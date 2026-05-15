"""
Import the India Insurance Database DOCX into the structured product catalog.

This is preferred over the PDF importer because the DOCX contains real tables.

Usage:
  python scripts/import_product_catalog_docx.py --dry-run
  python scripts/import_product_catalog_docx.py --limit-products 5 --dry-run
  python scripts/import_product_catalog_docx.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.import_product_catalog_pdf import (  # noqa: E402
    ParsedCompany,
    ParsedProduct,
    clean_text,
    import_catalog,
)


DEFAULT_DOCX = Path(r"C:\Users\MILAN\Downloads\India Insurance Database 2026.docx")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import product catalog DOCX into Supabase tables.")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX), help="Path to product catalog DOCX.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print summary without writing to Supabase.")
    parser.add_argument("--limit-products", type=int, default=0, help="Import only the first N parsed products.")
    parser.add_argument("--limit-companies", type=int, default=0, help="Import only the first N parsed companies.")
    parser.add_argument(
        "--write-change-log",
        action="store_true",
        help="Also write product_change_log rows. Off by default to keep reruns tidy.",
    )
    return parser.parse_args()


def iter_blocks(document: Document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            text = clean_text(Paragraph(child, document).text)
            yield {"type": "paragraph", "text": text}
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = [
                [clean_text(cell.text) for cell in row.cells]
                for row in table.rows
            ]
            yield {"type": "table", "rows": rows}


def table_header(block: dict[str, Any]) -> list[str]:
    if block.get("type") != "table" or not block.get("rows"):
        return []
    return block["rows"][0]


def is_master_company_table(block: dict[str, Any]) -> bool:
    return table_header(block) == ["Company Name", "Type", "Est.", "IRDAI Reg.", "HQ", "Website"]


def is_company_field_table(block: dict[str, Any]) -> bool:
    rows = block.get("rows") or []
    return (
        block.get("type") == "table"
        and table_header(block) in (["Field", "Details"], ["Field", "Detail"])
        and len(rows) > 1
        and rows[1][0] == "IRDAI Registration"
    )


def is_product_field_table(block: dict[str, Any]) -> bool:
    rows = block.get("rows") or []
    return (
        block.get("type") == "table"
        and table_header(block) in (["Field", "Details"], ["Field", "Detail"])
        and len(rows) > 1
        and rows[1][0] == "Product Type"
    )


def previous_paragraph(blocks: list[dict[str, Any]], index: int) -> str:
    cursor = index - 1
    while cursor >= 0:
        block = blocks[cursor]
        if block["type"] == "paragraph" and block["text"]:
            return block["text"]
        cursor -= 1
    return ""


def normalize_company_heading(value: str) -> str:
    value = re.sub(r"^2\.\d+\s+", "", value).strip()
    return value.replace("&", "and")


def normalize_company_name(value: str) -> str:
    normalized = clean_text(value).replace("&", "and")
    normalized = re.sub(r"\bTata\s+AIG\b", "TATA AIG", normalized, flags=re.IGNORECASE)
    return normalized


def rows_to_dict(rows: list[list[str]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        key = row[0].strip()
        value = row[1].strip()
        if key:
            output[key] = value
    return output


def next_special_table_index(blocks: list[dict[str, Any]], start: int) -> int:
    cursor = start
    while cursor < len(blocks):
        if is_company_field_table(blocks[cursor]) or is_product_field_table(blocks[cursor]):
            return cursor
        cursor += 1
    return len(blocks)


def parse_product_window(product: ParsedProduct, blocks: list[dict[str, Any]], start: int, end: int) -> None:
    mode: str | None = None
    for index in range(start, end):
        block = blocks[index]
        if block["type"] == "table":
            header = table_header(block)
            rows = block["rows"]
            if header == ["Benefit Type", "Details"]:
                for row in rows[1:]:
                    if len(row) >= 2 and row[0]:
                        product.benefits.append({"title": row[0], "description": row[1] or "N/A"})
                continue
            if header == ["Condition", "Details"]:
                for row in rows[1:]:
                    if len(row) >= 2 and row[0]:
                        product.conditions.append({"title": row[0], "description": row[1] or "N/A"})
                continue
            continue

        text = block["text"]
        if not text:
            continue
        if index + 1 < len(blocks) and is_product_field_table(blocks[index + 1]):
            continue
        if text in {"Key Features", "Benefits", "Policy Conditions", "Claim & Performance", "Ideal Customer Profile"}:
            mode = text
            continue

        if mode == "Key Features":
            product.key_features.append(text)
        elif mode == "Claim & Performance":
            product.claim_performance = clean_text(f"{product.claim_performance} {text}")
        elif mode == "Ideal Customer Profile":
            product.ideal_customer_profile = clean_text(f"{product.ideal_customer_profile} {text}")


def parse_docx(docx_path: Path) -> list[ParsedCompany]:
    document = Document(str(docx_path))
    blocks = list(iter_blocks(document))
    companies_by_name = parse_master_company_tables(blocks)
    current_company: ParsedCompany | None = None

    index = 0
    while index < len(blocks):
        block = blocks[index]

        if is_company_field_table(block):
            if current_company:
                companies_by_name[current_company.name] = current_company
            company_name = normalize_company_heading(previous_paragraph(blocks, index))
            existing = companies_by_name.get(company_name)
            current_company = ParsedCompany(
                name=company_name,
                page_refs=existing.page_refs if existing else [],
                fields={**(existing.fields if existing else {}), **rows_to_dict(block["rows"])},
                products=[],
            )
            index += 1
            continue

        if is_product_field_table(block) and current_company:
            product_name = previous_paragraph(blocks, index)
            product = ParsedProduct(
                name=product_name,
                fields=rows_to_dict(block["rows"]),
            )
            riders = product.fields.get("Riders", "")
            if riders:
                product.riders = [clean_text(item) for item in re.split(r";|,", riders) if clean_text(item)]

            end = next_special_table_index(blocks, index + 1)
            parse_product_window(product, blocks, index + 1, end)
            current_company.products.append(product)
            index = end
            continue

        index += 1

    if current_company:
        companies_by_name[current_company.name] = current_company

    return [company for company in companies_by_name.values() if company.name]


def parse_master_company_tables(blocks: list[dict[str, Any]]) -> dict[str, ParsedCompany]:
    companies: dict[str, ParsedCompany] = {}
    table_number = 0
    for block in blocks:
        if not is_master_company_table(block):
            continue
        table_number += 1
        insurer_category = category_for_master_table(table_number)
        for row in block["rows"][1:]:
            if len(row) < 6 or not row[0]:
                continue
            company_name = normalize_company_name(row[0])
            companies[company_name] = ParsedCompany(
                name=company_name,
                fields={
                    "Ownership Type": row[1],
                    "Established Year": row[2],
                    "IRDAI Registration": row[3],
                    "Headquarters": row[4],
                    "Website": row[5],
                    "Insurer Category": insurer_category,
                },
                products=[],
            )
    return companies


def category_for_master_table(table_number: int) -> str:
    if table_number == 1:
        return "life"
    if table_number == 2:
        return "general"
    if table_number in {3, 4}:
        return "standalone_health"
    if table_number == 5:
        return "reinsurance"
    return "general"


def limited_catalog(
    companies: list[ParsedCompany],
    limit_companies: int = 0,
    limit_products: int = 0,
) -> list[ParsedCompany]:
    if limit_companies:
        companies = companies[:limit_companies]
    if not limit_products:
        return companies

    remaining = limit_products
    limited: list[ParsedCompany] = []
    for company in companies:
        if remaining <= 0:
            break
        clone = ParsedCompany(
            name=company.name,
            page_refs=company.page_refs,
            fields=company.fields,
            products=company.products[:remaining],
        )
        limited.append(clone)
        remaining -= len(clone.products)
    return limited


def print_summary(companies: list[ParsedCompany]) -> None:
    total_products = sum(len(company.products) for company in companies)
    total_features = sum(len(product.key_features) for company in companies for product in company.products)
    total_benefits = sum(len(product.benefits) for company in companies for product in company.products)
    total_conditions = sum(len(product.conditions) for company in companies for product in company.products)
    total_riders = sum(len(product.riders) for company in companies for product in company.products)
    total_claim_rows = sum(1 for company in companies for product in company.products if product.claim_performance)
    total_profile_rows = sum(1 for company in companies for product in company.products if product.ideal_customer_profile)
    print(f"Parsed companies: {len(companies)}")
    print(f"Parsed products: {total_products}")
    print(f"Parsed feature rows: {total_features}")
    print(f"Parsed benefit rows: {total_benefits}")
    print(f"Parsed condition rows: {total_conditions}")
    print(f"Parsed rider/add-on rows: {total_riders}")
    print(f"Parsed claim performance rows: {total_claim_rows}")
    print(f"Parsed ideal customer profile rows: {total_profile_rows}")
    print("Product import will also create one product_import_batches row and one product_versions row per product.")
    for company in companies:
        print(f"- {company.name}: {len(company.products)} products")
        for product in company.products[:3]:
            print(
                f"  - {product.name} | {product.fields.get('Category')} | "
                f"{product.fields.get('Eligibility')}"
            )


def main() -> int:
    args = parse_args()
    docx_path = Path(args.docx).resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"Product catalog DOCX not found: {docx_path}")

    companies = limited_catalog(
        parse_docx(docx_path),
        limit_companies=args.limit_companies,
        limit_products=args.limit_products,
    )
    print_summary(companies)

    if args.dry_run:
        print("Dry run only. No Supabase writes performed.")
        return 0

    import_catalog(
        companies,
        limit_products=args.limit_products,
        source_document=docx_path.name,
        write_change_log=args.write_change_log,
    )
    print("DOCX product catalog import completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

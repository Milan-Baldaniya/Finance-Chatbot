"""
Import the India Insurance Database PDF into the structured product catalog.

Usage:
  python scripts/import_product_catalog_pdf.py --dry-run
  python scripts/import_product_catalog_pdf.py --limit-products 5 --dry-run
  python scripts/import_product_catalog_pdf.py

Run from the backend folder or pass --pdf explicitly.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import get_db


DEFAULT_PDF = Path(__file__).resolve().parents[1] / "docs" / "India Insurance Database 2026.pdf"
SOURCE_DOCUMENT = "India Insurance Database 2026.pdf"

COMPANY_SECTION_RE = re.compile(r"^2\.\d+\s+(.+)$")
PRODUCT_RE = re.compile(r"^[■▪]\s+(.+)$")

COMPANY_FIELDS = {
    "IRDAI Registration": "irdai_registration_no",
    "Headquarters": "headquarters",
    "Website": "website",
    "Background": "background",
    "Market Position": "market_position",
    "Key Segments": "key_segments",
}

PRODUCT_FIELDS = {
    "Product Type": "product_type",
    "Category": "product_category",
    "Launch Year": "launch_year",
    "Status": "current_status",
    "Eligibility": "eligibility_summary",
    "Policy Term": "policy_term",
    "Premium Pay Term": "premium_payment_term",
    "Min Sum Assured": "min_sum_assured",
    "Max Sum Assured": "max_sum_assured",
    "Premium Range": "premium_range",
    "Riders": "riders",
    "Tax Benefits": "tax_benefits",
}

SECTION_MARKERS = {
    "Field",
    "Detail",
    "Details",
    "Benefits",
    "Benefit Type",
    "Policy Conditions",
    "Condition",
    "Claim & Performance",
    "Ideal Customer Profile",
    "Key Features",
}


@dataclass
class ParsedProduct:
    name: str
    page_refs: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    key_features: list[str] = field(default_factory=list)
    benefits: list[dict[str, str]] = field(default_factory=list)
    conditions: list[dict[str, str]] = field(default_factory=list)
    riders: list[str] = field(default_factory=list)
    claim_performance: str = ""
    ideal_customer_profile: str = ""


@dataclass
class ParsedCompany:
    name: str
    page_refs: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    products: list[ParsedProduct] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import product catalog PDF into Supabase tables.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Path to product catalog PDF.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print summary without writing to Supabase.")
    parser.add_argument("--limit-products", type=int, default=0, help="Import only the first N parsed products.")
    parser.add_argument("--limit-companies", type=int, default=0, help="Import only the first N parsed companies.")
    return parser.parse_args()


def clean_text(value: str) -> str:
    value = value.replace("\x7f", "₹")
    value = value.replace("■", "₹").replace("▪", "₹")
    value = value.replace("", "-")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_line(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith(("■ ", "▪ ")):
        return "■ " + clean_text(stripped[2:])
    return clean_text(value).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def normalize_company_name(raw: str) -> str:
    return clean_text(raw).replace("&", "and")


def normalize_status(raw: str) -> str:
    value = clean_text(raw).lower()
    if "discontinued" in value:
        return "discontinued"
    if "legacy" in value:
        return "legacy"
    if "suspend" in value:
        return "suspended"
    if "upcoming" in value:
        return "upcoming"
    return "active"


def normalize_category(raw: str) -> str:
    value = clean_text(raw).lower()
    if "health" in value:
        return "health"
    if "motor" in value:
        return "motor"
    if "travel" in value:
        return "travel"
    if "home" in value:
        return "home"
    if "commercial" in value:
        return "commercial"
    if "reinsurance" in value:
        return "reinsurance"
    return "life"


def normalize_product_category(product: ParsedProduct) -> str:
    return normalize_category(
        " ".join(
            [
                product.fields.get("Category", ""),
                product.fields.get("Product Type", ""),
                product.name,
            ]
        )
    )


def infer_insurer_category(company_name: str, products: list[ParsedProduct]) -> str:
    name = company_name.lower()
    if "reinsurance" in name or "gic re" in name:
        return "reinsurance"
    if "health" in name or any(normalize_product_category(p) == "health" for p in products):
        if not any(normalize_product_category(p) in {"life", "motor"} for p in products):
            return "standalone_health"
    if "general" in name or any(normalize_product_category(p) == "motor" for p in products):
        return "general"
    return "life"


def extract_pdf_pages(pdf_path: Path) -> list[tuple[int, list[str]]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, list[str]]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = [clean_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        pages.append((index, lines))
    return pages


def parse_value_after(lines: list[str], start: int, stop_markers: set[str]) -> tuple[str, int]:
    values: list[str] = []
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line in stop_markers or line in COMPANY_FIELDS or line in PRODUCT_FIELDS:
            break
        if PRODUCT_RE.match(line) or COMPANY_SECTION_RE.match(line) or line.startswith("Active Products"):
            break
        values.append(line)
        index += 1
    return clean_text(" ".join(values)), index


def parse_company_fields(lines: list[str], start: int, end: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = start
    while index < end:
        line = lines[index]
        if line in COMPANY_FIELDS:
            value, next_index = parse_value_after(lines, index, set(COMPANY_FIELDS) | {"Active Products"})
            fields[line] = value
            index = next_index
            continue
        index += 1
    return fields


def next_marker_index(lines: list[str], start: int, markers: set[str]) -> int:
    index = start
    while index < len(lines):
        line = lines[index]
        if line in markers or PRODUCT_RE.match(line) or COMPANY_SECTION_RE.match(line):
            return index
        index += 1
    return len(lines)


def parse_key_features(lines: list[str], start: int, end: int) -> list[str]:
    features: list[str] = []
    for line in lines[start:end]:
        text = line.lstrip("-•▪■ ").strip()
        if text and text not in {"Field", "Detail"}:
            features.append(text)
    return features


def parse_pairs(lines: list[str], start: int, end: int, key_names: set[str]) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    index = start
    while index < end:
        key = lines[index]
        if key in {"Benefit Type", "Details", "Condition"}:
            index += 1
            continue
        if key not in key_names:
            index += 1
            continue
        value_lines: list[str] = []
        index += 1
        while index < end and lines[index] not in key_names and lines[index] not in SECTION_MARKERS:
            value_lines.append(lines[index])
            index += 1
        pairs.append({"title": key, "description": clean_text(" ".join(value_lines))})
    return pairs


def parse_product_block(name: str, page_ref: str, lines: list[str]) -> ParsedProduct:
    product = ParsedProduct(name=clean_text(name), page_refs=[page_ref])
    index = 0
    while index < len(lines):
        line = lines[index]
        if line in PRODUCT_FIELDS:
            value, next_index = parse_value_after(lines, index, set(PRODUCT_FIELDS) | SECTION_MARKERS)
            product.fields[line] = value
            index = next_index
            continue

        if line == "Key Features":
            end = next_marker_index(lines, index + 1, {"Benefits", "Policy Conditions", "Claim & Performance", "Ideal Customer Profile"})
            product.key_features.extend(parse_key_features(lines, index + 1, end))
            index = end
            continue

        if line == "Benefits":
            end = next_marker_index(lines, index + 1, {"Policy Conditions", "Claim & Performance", "Ideal Customer Profile"})
            product.benefits.extend(
                parse_pairs(
                    lines,
                    index + 1,
                    end,
                    {"Death Benefit", "Maturity Benefit", "Survival Benefit", "Restore Benefit", "Cashless Benefit", "No-Claim Bonus"},
                )
            )
            index = end
            continue

        if line == "Policy Conditions":
            end = next_marker_index(lines, index + 1, {"Claim & Performance", "Ideal Customer Profile"})
            product.conditions.extend(
                parse_pairs(
                    lines,
                    index + 1,
                    end,
                    {"Exclusions", "Surrender Value", "Loan Facility", "Waiting Period", "Cancellation"},
                )
            )
            index = end
            continue

        if line == "Claim & Performance":
            value, next_index = parse_value_after(lines, index, {"Ideal Customer Profile"})
            product.claim_performance = value
            index = next_index
            continue

        if line == "Ideal Customer Profile":
            value, next_index = parse_value_after(lines, index, set(PRODUCT_FIELDS) | SECTION_MARKERS)
            product.ideal_customer_profile = value
            index = next_index
            continue

        index += 1

    riders = product.fields.get("Riders", "")
    if riders:
        product.riders = [clean_text(item) for item in re.split(r";|,", riders) if clean_text(item)]
    return product


def parse_companies(pdf_path: Path) -> list[ParsedCompany]:
    pages = extract_pdf_pages(pdf_path)
    flattened: list[tuple[int, str]] = []
    for page_no, lines in pages:
        if page_no < 6 or page_no > 63:
            continue
        for line in lines:
            flattened.append((page_no, line))

    companies: list[ParsedCompany] = []
    current_company: ParsedCompany | None = None
    section_lines: list[tuple[int, str]] = []

    def flush_company() -> None:
        nonlocal section_lines, current_company
        if not current_company:
            return
        parse_company_section(current_company, section_lines)
        companies.append(current_company)
        section_lines = []

    for page_no, line in flattened:
        company_match = COMPANY_SECTION_RE.match(line)
        if company_match and "Section" not in line:
            flush_company()
            current_company = ParsedCompany(
                name=normalize_company_name(company_match.group(1)),
                page_refs=[str(page_no)],
            )
            section_lines = []
            continue
        if current_company:
            section_lines.append((page_no, line))

    flush_company()
    return companies


def parse_company_section(company: ParsedCompany, section_lines: list[tuple[int, str]]) -> None:
    lines = [line for _, line in section_lines]
    active_index = next((i for i, line in enumerate(lines) if line.startswith("Active Products")), len(lines))
    company.fields = parse_company_fields(lines, 0, active_index)

    product_indexes: list[tuple[int, str, str]] = []
    for index, (page_no, line) in enumerate(section_lines):
        match = PRODUCT_RE.match(line)
        if match:
            product_indexes.append((index, str(page_no), match.group(1)))

    for pos, (start, page_ref, product_name) in enumerate(product_indexes):
        end = product_indexes[pos + 1][0] if pos + 1 < len(product_indexes) else len(section_lines)
        block = [line for _, line in section_lines[start + 1 : end]]
        product = parse_product_block(product_name, page_ref, block)
        company.products.append(product)


def upsert_company(db, company: ParsedCompany, source_document: str = SOURCE_DOCUMENT) -> dict[str, Any]:
    ownership_type = clean_text(company.fields.get("Ownership Type", "")).lower() or None
    if ownership_type not in {"public", "private"}:
        ownership_type = None

    established_year = None
    if company.fields.get("Established Year"):
        match = re.search(r"\d{4}", company.fields["Established Year"])
        established_year = int(match.group(0)) if match else None

    insurer_category = company.fields.get("Insurer Category") or infer_insurer_category(company.name, company.products)

    payload = {
        "company_name": company.name,
        "company_slug": slugify(company.name),
        "insurer_category": insurer_category,
        "ownership_type": ownership_type,
        "irdai_registration_no": company.fields.get("IRDAI Registration"),
        "established_year": established_year,
        "headquarters": company.fields.get("Headquarters"),
        "website": company.fields.get("Website"),
        "background": company.fields.get("Background"),
        "market_position": company.fields.get("Market Position"),
        "key_segments": [
            clean_text(item)
            for item in re.split(r",|;", company.fields.get("Key Segments", ""))
            if clean_text(item)
        ],
        "status": "active",
        "source_document": source_document,
        "source_page_refs": company.page_refs,
    }
    response = db.table("insurance_companies").upsert(payload, on_conflict="company_slug").execute()
    if not response.data:
        raise RuntimeError(f"Failed to upsert company: {company.name}")
    return response.data[0]


def upsert_product(db, company_id: str, product: ParsedProduct, source_document: str = SOURCE_DOCUMENT) -> dict[str, Any]:
    launch_year = None
    if product.fields.get("Launch Year"):
        match = re.search(r"\d{4}", product.fields["Launch Year"])
        launch_year = int(match.group(0)) if match else None

    payload = {
        "company_id": company_id,
        "product_name": product.name,
        "product_slug": slugify(product.name),
        "plan_code": extract_plan_code(product.name),
        "product_category": normalize_product_category(product),
        "product_type": product.fields.get("Product Type"),
        "distribution_channel": infer_distribution_channel(product.fields.get("Product Type", "")),
        "launch_year": launch_year,
        "current_status": normalize_status(product.fields.get("Status", "")),
        "short_description": product.fields.get("Product Type"),
        "min_entry_age": extract_min_age(product.fields.get("Eligibility", "")),
        "max_entry_age": extract_max_age(product.fields.get("Eligibility", "")),
        "eligibility_summary": product.fields.get("Eligibility"),
        "policy_term": product.fields.get("Policy Term"),
        "premium_payment_term": product.fields.get("Premium Pay Term"),
        "min_sum_assured": product.fields.get("Min Sum Assured"),
        "max_sum_assured": product.fields.get("Max Sum Assured"),
        "premium_range": product.fields.get("Premium Range"),
        "tax_benefits": product.fields.get("Tax Benefits"),
        "source_document": source_document,
        "source_page_refs": product.page_refs,
    }
    response = db.table("insurance_products").upsert(
        payload,
        on_conflict="company_id,product_slug",
    ).execute()
    if not response.data:
        raise RuntimeError(f"Failed to upsert product: {product.name}")
    return response.data[0]


def extract_plan_code(name: str) -> str | None:
    match = re.search(r"\((Plan\s+\d+)\)", name, flags=re.IGNORECASE)
    return match.group(1) if match else None


def infer_distribution_channel(product_type: str) -> str | None:
    value = product_type.lower()
    if "online" in value:
        return "online"
    if "offline" in value:
        return "offline"
    return "mixed"


def extract_min_age(eligibility: str) -> str | None:
    match = re.search(r"(\d+\s*(?:days|months|years)?)\s*[–-]", eligibility, flags=re.IGNORECASE)
    return match.group(1) if match else None


def extract_max_age(eligibility: str) -> str | None:
    match = re.search(r"[–-]\s*(\d+\s*(?:days|months|years)?)", eligibility, flags=re.IGNORECASE)
    return match.group(1) if match else None


def delete_child_rows(db, product_id: str) -> None:
    for table in [
        "product_features",
        "product_benefits",
        "product_conditions",
        "product_riders_addons",
        "product_claim_performance",
        "product_ideal_customer_profiles",
    ]:
        db.table(table).delete().eq("product_id", product_id).execute()


def insert_product_children(db, product_id: str, product: ParsedProduct, source_document: str = SOURCE_DOCUMENT) -> None:
    feature_rows = [
        {
            "product_id": product_id,
            "feature_title": None,
            "feature_description": feature,
            "feature_type": "core_feature",
            "display_order": index,
        }
        for index, feature in enumerate(product.key_features, start=1)
    ]
    if feature_rows:
        db.table("product_features").insert(feature_rows).execute()

    benefit_rows = [
        {
            "product_id": product_id,
            "benefit_type": slugify(item["title"]).replace("-", "_"),
            "benefit_description": item["description"] or "N/A",
            "applies_to": "base_plan",
        }
        for item in product.benefits
    ]
    if benefit_rows:
        db.table("product_benefits").insert(benefit_rows).execute()

    condition_rows = [
        {
            "product_id": product_id,
            "condition_type": slugify(item["title"]).replace("-", "_"),
            "condition_title": item["title"],
            "condition_description": item["description"] or "N/A",
            "severity": "important",
        }
        for item in product.conditions
    ]
    if condition_rows:
        db.table("product_conditions").insert(condition_rows).execute()

    rider_rows = [
        {
            "product_id": product_id,
            "rider_name": rider,
            "rider_type": infer_rider_type(rider),
            "description": rider,
            "is_optional": True,
        }
        for rider in product.riders
    ]
    if rider_rows:
        db.table("product_riders_addons").insert(rider_rows).execute()

    if product.claim_performance:
        db.table("product_claim_performance").insert(
            {
                "product_id": product_id,
                "metric_name": "claim_settlement_ratio",
                "metric_value": product.claim_performance,
                "metric_year": infer_metric_year(product.claim_performance),
                "metric_context": product.claim_performance,
                "source_note": source_document,
            }
        ).execute()

    if product.ideal_customer_profile:
        db.table("product_ideal_customer_profiles").insert(
            {
                "product_id": product_id,
                "profile_summary": product.ideal_customer_profile,
                "customer_life_stage": infer_life_stages(product.ideal_customer_profile),
                "income_segment": infer_income_segments(product.ideal_customer_profile),
                "risk_profile": infer_risk_profiles(product.ideal_customer_profile),
                "recommended_for": [product.ideal_customer_profile],
                "not_recommended_for": [],
            }
        ).execute()


def infer_rider_type(rider: str) -> str | None:
    value = rider.lower()
    if "critical" in value:
        return "critical_illness"
    if "accident" in value or "accidental" in value:
        return "accidental_death"
    if "disability" in value:
        return "disability"
    if "maternity" in value:
        return "maternity"
    if "opd" in value:
        return "opd"
    return None


def infer_metric_year(text: str) -> str | None:
    match = re.search(r"(20\d{2}[–-]\d{2})", text)
    return match.group(1) if match else None


def infer_life_stages(text: str) -> list[str]:
    value = text.lower()
    stages = []
    if "senior" in value or "retire" in value:
        stages.append("senior_citizen")
    if "famil" in value:
        stages.append("family")
    if "young" in value:
        stages.append("young_professional")
    if "self-employed" in value or "self employed" in value:
        stages.append("self_employed")
    if "vehicle" in value:
        stages.append("vehicle_owner")
    return stages


def infer_income_segments(text: str) -> list[str]:
    value = text.lower()
    if "hni" in value or "high" in value:
        return ["high"]
    if "low cost" in value or "low premium" in value:
        return ["middle", "upper_middle"]
    return []


def infer_risk_profiles(text: str) -> list[str]:
    value = text.lower()
    profiles = []
    if "market" in value or "ulip" in value:
        profiles.append("market_linked")
    if "conservative" in value or "guaranteed" in value:
        profiles.append("conservative")
    if "protection" in value or "cover" in value:
        profiles.append("protection_focused")
    return profiles


def create_import_batch(db, source_document: str, companies: list[ParsedCompany]) -> dict[str, Any]:
    total_products = sum(len(company.products) for company in companies)
    response = db.table("product_import_batches").insert(
        {
            "source_document_name": source_document,
            "source_document_version": "2026 Edition",
            "import_status": "processing",
            "total_companies_detected": len(companies),
            "total_products_detected": total_products,
            "import_notes": "Structured import from product catalog source document.",
        }
    ).execute()
    if not response.data:
        raise RuntimeError("Failed to create product import batch.")
    return response.data[0]


def complete_import_batch(
    db,
    batch_id: str,
    products_added: int,
    products_updated: int,
    status: str = "completed",
    notes: str | None = None,
) -> None:
    payload = {
        "import_status": status,
        "total_products_added": products_added,
        "total_products_updated": products_updated,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if notes:
        payload["import_notes"] = notes
    db.table("product_import_batches").update(payload).eq("id", batch_id).execute()


def upsert_product_version(db, product_id: str, product: ParsedProduct, source_document: str) -> None:
    changed_fields = {
        "product_name": product.name,
        "fields": product.fields,
        "feature_count": len(product.key_features),
        "benefit_count": len(product.benefits),
        "condition_count": len(product.conditions),
        "rider_count": len(product.riders),
        "has_claim_performance": bool(product.claim_performance),
        "has_ideal_customer_profile": bool(product.ideal_customer_profile),
    }
    db.table("product_versions").upsert(
        {
            "product_id": product_id,
            "version_no": 1,
            "change_type": "imported",
            "change_summary": f"Initial structured import from {source_document}",
            "changed_fields": changed_fields,
            "approval_status": "approved",
            "source_type": "pdf_import",
            "source_reference": source_document,
        },
        on_conflict="product_id,version_no",
    ).execute()


def insert_product_change_log(db, product_id: str, product: ParsedProduct, source_document: str) -> None:
    db.table("product_change_log").insert(
        {
            "product_id": product_id,
            "action": "create",
            "field_name": "structured_product_import",
            "old_value": None,
            "new_value": product.name,
            "reason": f"Imported from {source_document}",
        }
    ).execute()


def import_catalog(
    companies: list[ParsedCompany],
    limit_products: int = 0,
    source_document: str = SOURCE_DOCUMENT,
    source_type: str = "pdf_import",
    write_change_log: bool = False,
) -> None:
    db = get_db()
    batch = create_import_batch(db, source_document, companies)
    imported_products = 0
    updated_products = 0
    try:
        for company in companies:
            company_row = upsert_company(db, company, source_document=source_document)
            for product in company.products:
                if limit_products and imported_products >= limit_products:
                    complete_import_batch(db, batch["id"], imported_products, updated_products)
                    return
                product_row = upsert_product(db, company_row["id"], product, source_document=source_document)
                delete_child_rows(db, product_row["id"])
                insert_product_children(db, product_row["id"], product, source_document=source_document)
                upsert_product_version(db, product_row["id"], product, source_document)
                if write_change_log:
                    insert_product_change_log(db, product_row["id"], product, source_document)
                imported_products += 1
                print(f"Imported {company.name} -> {product.name}")
        complete_import_batch(db, batch["id"], imported_products, updated_products)
    except Exception as exc:
        complete_import_batch(
            db,
            batch["id"],
            imported_products,
            updated_products,
            status="failed",
            notes=f"Import failed after {imported_products} products: {exc}",
        )
        raise


def print_summary(companies: list[ParsedCompany]) -> None:
    total_products = sum(len(company.products) for company in companies)
    print(f"Parsed companies: {len(companies)}")
    print(f"Parsed products: {total_products}")
    for company in companies:
        print(f"- {company.name}: {len(company.products)} products")
        for product in company.products[:3]:
            print(f"  - {product.name} | {product.fields.get('Category')} | {product.fields.get('Eligibility')}")


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Product catalog PDF not found: {pdf_path}")

    companies = parse_companies(pdf_path)
    if args.limit_companies:
        companies = companies[: args.limit_companies]
    if args.limit_products:
        remaining = args.limit_products
        limited_companies: list[ParsedCompany] = []
        for company in companies:
            if remaining <= 0:
                break
            clone = ParsedCompany(company.name, company.page_refs, company.fields, company.products[:remaining])
            limited_companies.append(clone)
            remaining -= len(clone.products)
        companies = limited_companies

    print_summary(companies)
    if args.dry_run:
        print("Dry run only. No Supabase writes performed.")
        return 0

    import_catalog(companies)
    print("Product catalog import completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Generate Supabase seed SQL from the product catalog Excel workbook.

Default input:
  India_Insurance_Database_Supabase_Import.xlsx

Output:
  backend/seed_india_insurance_database_supabase_import.sql
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = REPO_ROOT / "India_Insurance_Database_Supabase_Import.xlsx"
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "seed_india_insurance_database_supabase_import.sql"

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate product seed SQL from XLSX.")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter.upper()) - ord("A") + 1)
    return value - 1


def load_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [
        "".join(
            node.text or ""
            for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
        )
        for item in root.findall("a:si", NS)
    ]


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or ""
            for node in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
        ).strip()

    value_node = cell.find("a:v", NS)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    return shared_strings[int(raw)].strip() if cell_type == "s" else raw.strip()


def normalize_target(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def sheet_paths(zf: ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_by_id = {
        rel.attrib["Id"]: normalize_target(rel.attrib["Target"])
        for rel in rels.findall("rel:Relationship", REL_NS)
    }
    output = []
    for sheet in workbook.find("a:sheets", NS):
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        output.append((sheet.attrib["name"], rel_by_id[rel_id]))
    return output


def read_sheet(zf: ZipFile, path: str, shared_strings: list[str]) -> list[dict[str, str]]:
    root = ET.fromstring(zf.read(path))
    rows: list[list[str]] = []
    for row in root.findall("a:sheetData/a:row", NS):
        values: list[str] = []
        for cell in row.findall("a:c", NS):
            idx = column_index(cell.attrib.get("r", "")) if cell.attrib.get("r") else len(values)
            while len(values) <= idx:
                values.append("")
            values[idx] = cell_value(cell, shared_strings)
        if any(values):
            rows.append(values)

    if not rows:
        return []
    headers = [header.strip() for header in rows[0]]
    records = []
    for row in rows[1:]:
        record = {
            header: (row[index].strip() if index < len(row) else "")
            for index, header in enumerate(headers)
            if header
        }
        if any(record.values()):
            records.append(record)
    return records


def read_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    with ZipFile(path) as zf:
        shared_strings = load_shared_strings(zf)
        workbook: dict[str, list[dict[str, str]]] = {}
        for name, sheet_path in sheet_paths(zf):
            if name.startswith("_") or name.lower() == "readme":
                continue
            workbook[name] = read_sheet(zf, sheet_path, shared_strings)
        return workbook


def sql_string(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return "'" + value.replace("'", "''") + "'"


def sql_int(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    match = re.search(r"-?\d+", str(value))
    return match.group(0) if match else "null"


def sql_bool(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return "true" if str(value).strip().lower() in {"true", "1", "yes", "y"} else "false"


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r",|;", value) if item.strip()]


def sql_text_array(value: str | None) -> str:
    items = split_list(value)
    if not items:
        return "array[]::text[]"
    return "array[" + ", ".join(sql_string(item) for item in items) + "]::text[]"


def product_id_subquery(product_slug: str) -> str:
    return f"(select id from public.insurance_products where product_slug = {sql_string(product_slug)} limit 1)"


def company_id_subquery(company_slug: str) -> str:
    return f"(select id from public.insurance_companies where company_slug = {sql_string(company_slug)} limit 1)"


def dedupe_by(records: list[dict[str, str]], key: str) -> list[dict[str, str]]:
    deduped: OrderedDict[str, dict[str, str]] = OrderedDict()
    for record in records:
        value = record.get(key, "").strip()
        if value:
            deduped[value] = record
    return list(deduped.values())


def values_block(rows: list[str]) -> str:
    return ",\n".join(rows)


def generate_sql(workbook: dict[str, list[dict[str, str]]], source_file: str) -> str:
    companies = dedupe_by(workbook.get("insurance_companies", []), "company_slug")
    products = dedupe_by(workbook.get("insurance_products", []), "product_slug")
    product_slugs = [row["product_slug"] for row in products if row.get("product_slug")]
    product_slug_list = ", ".join(sql_string(slug) for slug in product_slugs)

    lines = [
        "-- Generated from India_Insurance_Database_Supabase_Import.xlsx",
        f"-- Generated at {datetime.now(timezone.utc).isoformat()}",
        "-- Safe to rerun: master tables use upsert; child rows are refreshed for workbook products.",
        "",
        "begin;",
        "",
    ]

    lines.append("-- Import batch metadata")
    lines.append(
        "insert into public.product_import_batches "
        "(source_document_name, source_document_version, import_status, total_companies_detected, "
        "total_products_detected, total_products_added, total_products_updated, import_notes, completed_at) "
        f"values ({sql_string(source_file)}, '2026 Edition', 'completed', {len(companies)}, {len(products)}, "
        f"{len(products)}, 0, 'Seed SQL generated from Excel workbook', now());"
    )
    lines.append("")

    if companies:
        rows = []
        for row in companies:
            rows.append(
                "("
                + ", ".join(
                    [
                        sql_string(row.get("company_name")),
                        sql_string(row.get("company_slug")),
                        sql_string(row.get("insurer_category")),
                        sql_string(row.get("ownership_type")),
                        sql_string(row.get("irdai_registration_no")),
                        sql_int(row.get("established_year")),
                        sql_string(row.get("headquarters")),
                        sql_string(row.get("website")),
                        sql_string(row.get("background")),
                        sql_string(row.get("market_position")),
                        sql_text_array(row.get("key_segments")),
                        sql_string(row.get("status") or "active"),
                        sql_string(row.get("source_document")),
                        sql_text_array(row.get("source_page_refs")),
                    ]
                )
                + ")"
            )
        lines.append("-- insurance_companies")
        lines.append(
            "insert into public.insurance_companies "
            "(company_name, company_slug, insurer_category, ownership_type, irdai_registration_no, "
            "established_year, headquarters, website, background, market_position, key_segments, "
            "status, source_document, source_page_refs) values\n"
            + values_block(rows)
            + "\non conflict (company_slug) do update set\n"
            "company_name = excluded.company_name,\n"
            "insurer_category = excluded.insurer_category,\n"
            "ownership_type = excluded.ownership_type,\n"
            "irdai_registration_no = excluded.irdai_registration_no,\n"
            "established_year = excluded.established_year,\n"
            "headquarters = excluded.headquarters,\n"
            "website = excluded.website,\n"
            "background = excluded.background,\n"
            "market_position = excluded.market_position,\n"
            "key_segments = excluded.key_segments,\n"
            "status = excluded.status,\n"
            "source_document = excluded.source_document,\n"
            "source_page_refs = excluded.source_page_refs;"
        )
        lines.append("")

    if products:
        rows = []
        for row in products:
            rows.append(
                "("
                + ", ".join(
                    [
                        company_id_subquery(row.get("company_slug", "")),
                        sql_string(row.get("product_name")),
                        sql_string(row.get("product_slug")),
                        sql_string(row.get("plan_code")),
                        sql_string(row.get("product_category")),
                        sql_string(row.get("product_type")),
                        sql_string(row.get("distribution_channel")),
                        sql_int(row.get("launch_year")),
                        sql_string(row.get("current_status") or "active"),
                        sql_string(row.get("status_reason")),
                        sql_string(row.get("short_description")),
                        sql_string(row.get("min_entry_age")),
                        sql_string(row.get("max_entry_age")),
                        sql_string(row.get("eligibility_summary")),
                        sql_string(row.get("policy_term")),
                        sql_string(row.get("premium_payment_term")),
                        sql_string(row.get("min_sum_assured")),
                        sql_string(row.get("max_sum_assured")),
                        sql_string(row.get("premium_range")),
                        sql_string(row.get("tax_benefits")),
                        sql_string(row.get("source_document")),
                        sql_text_array(row.get("source_page_refs")),
                    ]
                )
                + ")"
            )
        lines.append("-- insurance_products")
        lines.append(
            "insert into public.insurance_products "
            "(company_id, product_name, product_slug, plan_code, product_category, product_type, "
            "distribution_channel, launch_year, current_status, status_reason, short_description, "
            "min_entry_age, max_entry_age, eligibility_summary, policy_term, premium_payment_term, "
            "min_sum_assured, max_sum_assured, premium_range, tax_benefits, source_document, source_page_refs) values\n"
            + values_block(rows)
            + "\non conflict (company_id, product_slug) do update set\n"
            "product_name = excluded.product_name,\n"
            "plan_code = excluded.plan_code,\n"
            "product_category = excluded.product_category,\n"
            "product_type = excluded.product_type,\n"
            "distribution_channel = excluded.distribution_channel,\n"
            "launch_year = excluded.launch_year,\n"
            "current_status = excluded.current_status,\n"
            "status_reason = excluded.status_reason,\n"
            "short_description = excluded.short_description,\n"
            "min_entry_age = excluded.min_entry_age,\n"
            "max_entry_age = excluded.max_entry_age,\n"
            "eligibility_summary = excluded.eligibility_summary,\n"
            "policy_term = excluded.policy_term,\n"
            "premium_payment_term = excluded.premium_payment_term,\n"
            "min_sum_assured = excluded.min_sum_assured,\n"
            "max_sum_assured = excluded.max_sum_assured,\n"
            "premium_range = excluded.premium_range,\n"
            "tax_benefits = excluded.tax_benefits,\n"
            "source_document = excluded.source_document,\n"
            "source_page_refs = excluded.source_page_refs;"
        )
        lines.append("")

    if product_slugs:
        lines.append("-- Refresh product child rows for workbook products")
        for table in [
            "product_features",
            "product_benefits",
            "product_conditions",
            "product_riders_addons",
            "product_claim_performance",
            "product_ideal_customer_profiles",
        ]:
            lines.append(
                f"delete from public.{table} where product_id in "
                f"(select id from public.insurance_products where product_slug in ({product_slug_list}));"
            )
        lines.append("")

    insert_child_tables(lines, workbook)

    if products:
        rows = []
        for row in products:
            rows.append(
                "("
                + ", ".join(
                    [
                        product_id_subquery(row["product_slug"]),
                        "1",
                        "'imported'",
                        sql_string(f"Initial seed import for {row.get('product_name')}"),
                        "'{}'::jsonb",
                        "'approved'",
                        "'pdf_import'",
                        sql_string(source_file),
                    ]
                )
                + ")"
            )
        lines.append("-- product_versions")
        lines.append(
            "insert into public.product_versions "
            "(product_id, version_no, change_type, change_summary, changed_fields, approval_status, source_type, source_reference) values\n"
            + values_block(rows)
            + "\non conflict (product_id, version_no) do update set\n"
            "change_type = excluded.change_type,\n"
            "change_summary = excluded.change_summary,\n"
            "changed_fields = excluded.changed_fields,\n"
            "approval_status = excluded.approval_status,\n"
            "source_type = excluded.source_type,\n"
            "source_reference = excluded.source_reference;"
        )
        lines.append("")

    lines.extend(["commit;", ""])
    return "\n".join(lines)


def insert_child_tables(lines: list[str], workbook: dict[str, list[dict[str, str]]]) -> None:
    table_specs = {
        "product_features": (
            ["product_id", "feature_title", "feature_description", "feature_type", "display_order"],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("feature_title")),
                sql_string(row.get("feature_description")),
                sql_string(row.get("feature_type")),
                sql_int(row.get("display_order")),
            ],
        ),
        "product_benefits": (
            ["product_id", "benefit_type", "benefit_description", "applies_to"],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("benefit_type")),
                sql_string(row.get("benefit_description")),
                sql_string(row.get("applies_to")),
            ],
        ),
        "product_conditions": (
            ["product_id", "condition_type", "condition_title", "condition_description", "severity"],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("condition_type")),
                sql_string(row.get("condition_title")),
                sql_string(row.get("condition_description")),
                sql_string(row.get("severity")),
            ],
        ),
        "product_riders_addons": (
            ["product_id", "rider_name", "rider_type", "description", "is_optional"],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("rider_name")),
                sql_string(row.get("rider_type")),
                sql_string(row.get("description")),
                sql_bool(row.get("is_optional")),
            ],
        ),
        "product_claim_performance": (
            ["product_id", "metric_name", "metric_value", "metric_year", "metric_context", "source_note"],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("metric_name")),
                sql_string(row.get("metric_value")),
                sql_string(row.get("metric_year")),
                sql_string(row.get("metric_context")),
                sql_string(row.get("source_note")),
            ],
        ),
        "product_ideal_customer_profiles": (
            [
                "product_id",
                "profile_summary",
                "customer_life_stage",
                "income_segment",
                "risk_profile",
                "recommended_for",
                "not_recommended_for",
            ],
            lambda row: [
                product_id_subquery(row.get("product_slug", "")),
                sql_string(row.get("profile_summary")),
                sql_text_array(row.get("customer_life_stage")),
                sql_text_array(row.get("income_segment")),
                sql_text_array(row.get("risk_profile")),
                sql_text_array(row.get("recommended_for")),
                sql_text_array(row.get("not_recommended_for")),
            ],
        ),
    }

    for table_name, (columns, build_values) in table_specs.items():
        records = workbook.get(table_name, [])
        if not records:
            continue
        rows = ["(" + ", ".join(build_values(row)) + ")" for row in records if row.get("product_slug")]
        if not rows:
            continue
        lines.append(f"-- {table_name}")
        lines.append(
            f"insert into public.{table_name} ({', '.join(columns)}) values\n"
            + values_block(rows)
            + ";"
        )
        lines.append("")


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    output_path = Path(args.output).resolve()
    workbook = read_workbook(xlsx_path)
    sql = generate_sql(workbook, xlsx_path.name)
    output_path.write_text(sql, encoding="utf-8")
    print(f"Wrote {output_path}")
    for sheet_name, records in workbook.items():
        print(f"{sheet_name}: {len(records)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

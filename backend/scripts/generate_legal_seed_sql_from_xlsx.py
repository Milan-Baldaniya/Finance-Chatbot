"""
Generate Supabase legal/handbook seed SQL from Insurance_DB_Seed_Data_v2.xlsx.

Output:
  backend/seed_insurance_db_seed_data_v3.sql
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_product_seed_sql_from_xlsx import (  # noqa: E402
    read_workbook,
    sql_bool,
    sql_int,
    sql_string,
    sql_text_array,
    values_block,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = REPO_ROOT / "Insurance_DB_Seed_Data_v2.xlsx"
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "seed_insurance_db_seed_data_v3.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate legal seed SQL from XLSX.")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def first_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row:
            return row.get(name, "")
    return ""


def source_id_subquery(source_name: str) -> str:
    return f"(select id from public.law_sources where source_name = {sql_string(source_name)} limit 1)"


def category_id_subquery(category_code: str) -> str:
    return f"(select id from public.legal_categories where category_code = {sql_string(category_code)} limit 1)"


def instrument_id_subquery(instrument_name: str) -> str:
    return f"(select id from public.legal_instruments where instrument_name = {sql_string(instrument_name)} limit 1)"


def provision_id_subquery(provision_code: str) -> str:
    return f"(select id from public.legal_provisions where provision_code = {sql_string(provision_code)} limit 1)"


def violation_type_id_subquery(category: str) -> str:
    return f"(select id from public.violation_types where violation_category = {sql_string(category)} limit 1)"


def grievance_id_for_tier(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return "null"
    return f"(select id from public.grievance_channels where tier_no = {digits} limit 1)"


def insert_where_not_exists(table: str, columns: list[str], row_values: list[str], exists_sql: str) -> str:
    return (
        f"insert into public.{table} ({', '.join(columns)})\n"
        f"select {', '.join(row_values)}\n"
        f"where not exists ({exists_sql});"
    )


def generate_sql(workbook: dict[str, list[dict[str, str]]], source_file: str) -> str:
    lines = [
        "-- Generated from Insurance_DB_Seed_Data_v2.xlsx",
        f"-- Generated at {datetime.now(timezone.utc).isoformat()}",
        "-- Uses natural-key insert guards where unique constraints are not present.",
        "",
        "begin;",
        "",
    ]

    law_sources = workbook.get("law_sources", [])
    if law_sources:
        lines.append("-- law_sources")
        for row in law_sources:
            source_name = row.get("source_name", "")
            lines.append(
                insert_where_not_exists(
                    "law_sources",
                    [
                        "source_name",
                        "source_type",
                        "version_label",
                        "effective_from",
                        "effective_to",
                        "is_active",
                        "notes",
                    ],
                    [
                        sql_string(source_name),
                        sql_string(row.get("source_type") or "pdf"),
                        sql_string(row.get("version_label")),
                        sql_string(row.get("effective_from")),
                        sql_string(row.get("effective_to")),
                        sql_bool(row.get("is_active")),
                        sql_string(row.get("notes")),
                    ],
                    f"select 1 from public.law_sources where source_name = {sql_string(source_name)}",
                )
            )
        lines.append("")

    categories = workbook.get("legal_categories", [])
    if categories:
        rows = []
        for row in categories:
            rows.append(
                "("
                + ", ".join(
                    [
                        sql_string(row.get("category_name")),
                        sql_string(row.get("category_code")),
                        sql_string(row.get("description")),
                        sql_int(row.get("display_order")),
                        sql_bool(row.get("is_active")),
                    ]
                )
                + ")"
            )
        lines.append("-- legal_categories")
        lines.append(
            "insert into public.legal_categories "
            "(category_name, category_code, description, display_order, is_active) values\n"
            + values_block(rows)
            + "\non conflict (category_code) do update set\n"
            "category_name = excluded.category_name,\n"
            "description = excluded.description,\n"
            "display_order = excluded.display_order,\n"
            "is_active = excluded.is_active;"
        )
        lines.append("")

    instruments = workbook.get("legal_instruments", [])
    if instruments:
        lines.append("-- legal_instruments")
        for row in instruments:
            instrument_name = row.get("instrument_name", "")
            values = [
                category_id_subquery(first_value(row, "⚙ category_code (ref → category_id)", "category_code")),
                sql_string(instrument_name),
                sql_string(row.get("instrument_type")),
                sql_int(row.get("year")),
                sql_string(row.get("regulator_or_authority")),
                sql_string(row.get("purpose")),
                sql_string(row.get("applicability")),
                sql_string(row.get("current_status") or "active"),
                source_id_subquery(first_value(row, "⚙ source_name (ref → source_id)", "source_name")),
                sql_string(row.get("valid_from")),
                sql_string(row.get("valid_to")),
                sql_bool(row.get("is_active")),
            ]
            lines.append(
                insert_where_not_exists(
                    "legal_instruments",
                    [
                        "category_id",
                        "instrument_name",
                        "instrument_type",
                        "year",
                        "regulator_or_authority",
                        "purpose",
                        "applicability",
                        "current_status",
                        "source_id",
                        "valid_from",
                        "valid_to",
                        "is_active",
                    ],
                    values,
                    f"select 1 from public.legal_instruments where instrument_name = {sql_string(instrument_name)}",
                )
            )
        lines.append("")

    provisions = workbook.get("legal_provisions", [])
    if provisions:
        lines.append("-- legal_provisions")
        for row in provisions:
            provision_code = row.get("provision_code", "")
            instrument_name = first_value(row, "⚙ instrument_name (ref → instrument_id)", "instrument_name")
            values = [
                instrument_id_subquery(instrument_name),
                sql_string(provision_code),
                sql_string(row.get("provision_title")),
                sql_string(row.get("provision_type")),
                sql_string(row.get("summary")),
                sql_string(row.get("practical_meaning")),
                sql_text_array(first_value(row, "applies_to (comma-separated)", "applies_to")),
                sql_bool(row.get("is_active")),
                source_id_subquery(first_value(row, "⚙ source_name (ref → source_id)", "source_name")),
            ]
            lines.append(
                insert_where_not_exists(
                    "legal_provisions",
                    [
                        "instrument_id",
                        "provision_code",
                        "provision_title",
                        "provision_type",
                        "summary",
                        "practical_meaning",
                        "applies_to",
                        "is_active",
                        "source_id",
                    ],
                    values,
                    f"select 1 from public.legal_provisions where provision_code = {sql_string(provision_code)}",
                )
            )
        lines.append("")

    add_simple_dependent_tables(lines, workbook)

    lines.append("-- legal_change_log")
    lines.append("-- Skipped intentionally: workbook contains placeholder entity_id values, not real UUIDs.")
    lines.append("")
    lines.append("commit;")
    lines.append("")
    return "\n".join(lines)


def add_simple_dependent_tables(lines: list[str], workbook: dict[str, list[dict[str, str]]]) -> None:
    requirements = workbook.get("regulatory_requirements", [])
    if requirements:
        lines.append("-- regulatory_requirements")
        for row in requirements:
            provision_code = first_value(row, "⚙ provision_code (ref → provision_id)", "provision_code")
            name = row.get("requirement_name", "")
            lines.append(
                insert_where_not_exists(
                    "regulatory_requirements",
                    [
                        "provision_id",
                        "requirement_name",
                        "requirement_description",
                        "applicable_entity",
                        "requirement_value",
                        "unit",
                        "deadline_days",
                        "frequency",
                        "is_mandatory",
                        "is_active",
                    ],
                    [
                        provision_id_subquery(provision_code),
                        sql_string(name),
                        sql_string(row.get("requirement_description")),
                        sql_string(row.get("applicable_entity")),
                        sql_string(row.get("requirement_value")),
                        sql_string(row.get("unit")),
                        sql_int(row.get("deadline_days")),
                        sql_string(row.get("frequency")),
                        sql_bool(row.get("is_mandatory")),
                        sql_bool(row.get("is_active")),
                    ],
                    f"select 1 from public.regulatory_requirements where requirement_name = {sql_string(name)}",
                )
            )
        lines.append("")

    intermediaries = workbook.get("intermediary_types", [])
    if intermediaries:
        lines.append("-- intermediary_types")
        for row in intermediaries:
            name = row.get("intermediary_name", "")
            lines.append(
                insert_where_not_exists(
                    "intermediary_types",
                    [
                        "intermediary_name",
                        "represents",
                        "max_insurers",
                        "min_qualification",
                        "training_requirement",
                        "key_compliance",
                        "min_net_worth",
                        "licence_requirement",
                        "is_active",
                    ],
                    [
                        sql_string(name),
                        sql_string(row.get("represents")),
                        sql_string(row.get("max_insurers")),
                        sql_string(row.get("min_qualification")),
                        sql_string(row.get("training_requirement")),
                        sql_string(row.get("key_compliance")),
                        sql_string(row.get("min_net_worth")),
                        sql_string(row.get("licence_requirement")),
                        sql_bool(row.get("is_active")),
                    ],
                    f"select 1 from public.intermediary_types where intermediary_name = {sql_string(name)}",
                )
            )
        lines.append("")

    rights = workbook.get("policyholder_rights", [])
    if rights:
        lines.append("-- policyholder_rights")
        for row in rights:
            name = row.get("right_name", "")
            provision_code = first_value(row, "⚙ provision_code (ref → related_provision_id)", "provision_code")
            lines.append(
                insert_where_not_exists(
                    "policyholder_rights",
                    [
                        "right_name",
                        "right_category",
                        "description",
                        "applicable_insurance_type",
                        "time_limit",
                        "refund_or_compensation_rule",
                        "escalation_available",
                        "related_provision_id",
                        "is_active",
                    ],
                    [
                        sql_string(name),
                        sql_string(row.get("right_category")),
                        sql_string(row.get("description")),
                        sql_text_array(first_value(row, "applicable_insurance_type (comma-separated)", "applicable_insurance_type")),
                        sql_string(row.get("time_limit")),
                        sql_string(row.get("refund_or_compensation_rule")),
                        sql_bool(row.get("escalation_available")),
                        provision_id_subquery(provision_code),
                        sql_bool(row.get("is_active")),
                    ],
                    f"select 1 from public.policyholder_rights where right_name = {sql_string(name)}",
                )
            )
        lines.append("")

    grievances = workbook.get("grievance_channels", [])
    if grievances:
        lines.append("-- grievance_channels")
        pending_grievance_updates: list[tuple[str, str]] = []
        for row in grievances:
            tier_no = sql_int(row.get("tier_no"))
            forum = row.get("forum_name", "")
            next_ref = first_value(row, "next_escalation (tier ref → next_escalation_id)", "next_escalation")
            if next_ref:
                pending_grievance_updates.append((tier_no, next_ref))
            lines.append(
                insert_where_not_exists(
                    "grievance_channels",
                    [
                        "tier_no",
                        "forum_name",
                        "access_method",
                        "time_limit",
                        "max_compensation",
                        "scope",
                        "next_escalation_id",
                        "is_active",
                    ],
                    [
                        tier_no,
                        sql_string(forum),
                        sql_string(row.get("access_method")),
                        sql_string(row.get("time_limit")),
                        sql_string(row.get("max_compensation")),
                        sql_string(row.get("scope")),
                        grievance_id_for_tier(next_ref),
                        sql_bool(row.get("is_active")),
                    ],
                    f"select 1 from public.grievance_channels where tier_no = {tier_no}",
                )
            )
        for tier_no, next_ref in pending_grievance_updates:
            lines.append(
                "update public.grievance_channels "
                f"set next_escalation_id = {grievance_id_for_tier(next_ref)} "
                f"where tier_no = {tier_no};"
            )
        lines.append("")

    violations = workbook.get("violation_types", [])
    if violations:
        lines.append("-- violation_types")
        for row in violations:
            category = row.get("violation_category", "")
            example = row.get("example_violation", "")
            provision_code = first_value(row, "⚙ provision_code (ref → related_provision_id)", "provision_code")
            lines.append(
                insert_where_not_exists(
                    "violation_types",
                    [
                        "violation_category",
                        "example_violation",
                        "responsible_party",
                        "related_provision_id",
                        "is_active",
                    ],
                    [
                        sql_string(category),
                        sql_string(example),
                        sql_string(row.get("responsible_party")),
                        provision_id_subquery(provision_code),
                        sql_bool(row.get("is_active")),
                    ],
                    "select 1 from public.violation_types "
                    f"where violation_category = {sql_string(category)} and example_violation = {sql_string(example)}",
                )
            )
        lines.append("")

    penalties = workbook.get("penalties", [])
    if penalties:
        lines.append("-- penalties")
        for row in penalties:
            category = first_value(row, "⚙ violation_category (ref → violation_type_id)", "violation_category")
            title = row.get("penalty_title", "")
            lines.append(
                insert_where_not_exists(
                    "penalties",
                    [
                        "violation_type_id",
                        "penalty_title",
                        "penalty_description",
                        "max_penalty_amount",
                        "penalty_unit",
                        "consequence",
                        "authority",
                        "is_active",
                    ],
                    [
                        violation_type_id_subquery(category),
                        sql_string(title),
                        sql_string(row.get("penalty_description")),
                        sql_int(row.get("max_penalty_amount")),
                        sql_string(row.get("penalty_unit") or "INR"),
                        sql_string(row.get("consequence")),
                        sql_string(row.get("authority") or "IRDAI"),
                        sql_bool(row.get("is_active")),
                    ],
                    f"select 1 from public.penalties where penalty_title = {sql_string(title)}",
                )
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
    for sheet_name, rows in workbook.items():
        print(f"{sheet_name}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

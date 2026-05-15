"""
Admin CRUD API for structured insurance product and legal handbook tables.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_admin_user
from app.core.db import get_db
from app.services.legal_knowledge import clear_legal_cache
from app.services.product_catalog_db import clear_product_catalog_cache


class TableConfig(BaseModel):
    name: str
    label: str
    group: str
    description: str
    columns: list[str]
    required: list[str] = []
    readonly: list[str] = []
    textarea: list[str] = []
    arrays: list[str] = []
    booleans: list[str] = []
    numbers: list[str] = []
    dates: list[str] = []
    json: list[str] = []
    search: list[str] = []
    order_by: str = "created_at"


class RowPayload(BaseModel):
    data: dict[str, Any]


router = APIRouter(
    prefix="/api/admin/data",
    tags=["admin-data"],
    dependencies=[Depends(get_current_admin_user)],
)


TABLES: dict[str, TableConfig] = {
    "insurance_companies": TableConfig(
        name="insurance_companies",
        label="Insurance Companies",
        group="Product Catalog",
        description="Insurer master records and company-level classification.",
        columns=[
            "company_name", "company_slug", "insurer_category", "ownership_type",
            "irdai_registration_no", "established_year", "headquarters", "website",
            "background", "market_position", "key_segments", "status",
            "source_document", "source_page_refs",
        ],
        required=["company_name", "company_slug", "insurer_category"],
        textarea=["background", "market_position"],
        arrays=["key_segments", "source_page_refs"],
        numbers=["established_year"],
        search=["company_name", "company_slug", "insurer_category", "website"],
    ),
    "insurance_products": TableConfig(
        name="insurance_products",
        label="Insurance Products",
        group="Product Catalog",
        description="Product master records linked to insurance companies.",
        columns=[
            "company_id", "product_name", "product_slug", "plan_code",
            "product_category", "product_type", "distribution_channel", "launch_year",
            "current_status", "status_reason", "short_description", "min_entry_age",
            "max_entry_age", "eligibility_summary", "policy_term",
            "premium_payment_term", "min_sum_assured", "max_sum_assured",
            "premium_range", "tax_benefits", "source_document", "source_page_refs",
        ],
        required=["company_id", "product_name", "product_slug", "product_category"],
        textarea=["status_reason", "short_description", "eligibility_summary", "tax_benefits"],
        arrays=["source_page_refs"],
        numbers=["launch_year"],
        search=["product_name", "product_slug", "plan_code", "product_category", "product_type"],
    ),
    "product_features": TableConfig(
        name="product_features",
        label="Product Features",
        group="Product Catalog",
        description="Core, optional, digital, network, financial, and policy features.",
        columns=["product_id", "feature_title", "feature_description", "feature_type", "display_order"],
        required=["product_id", "feature_description"],
        textarea=["feature_description"],
        numbers=["display_order"],
        search=["feature_title", "feature_description", "feature_type"],
    ),
    "product_benefits": TableConfig(
        name="product_benefits",
        label="Product Benefits",
        group="Product Catalog",
        description="Benefit descriptions for base plans, variants, riders, and add-ons.",
        columns=["product_id", "benefit_type", "benefit_description", "applies_to"],
        required=["product_id", "benefit_type", "benefit_description"],
        textarea=["benefit_description"],
        search=["benefit_type", "benefit_description", "applies_to"],
    ),
    "product_conditions": TableConfig(
        name="product_conditions",
        label="Product Conditions",
        group="Product Catalog",
        description="Eligibility conditions, exclusions, restrictions, and compliance-critical notes.",
        columns=["product_id", "condition_type", "condition_title", "condition_description", "severity"],
        required=["product_id", "condition_type", "condition_description"],
        textarea=["condition_description"],
        search=["condition_type", "condition_title", "condition_description", "severity"],
    ),
    "product_riders_addons": TableConfig(
        name="product_riders_addons",
        label="Riders & Add-ons",
        group="Product Catalog",
        description="Optional and bundled riders/add-ons associated with products.",
        columns=["product_id", "rider_name", "rider_type", "description", "is_optional"],
        required=["product_id", "rider_name"],
        textarea=["description"],
        booleans=["is_optional"],
        search=["rider_name", "rider_type", "description"],
    ),
    "product_claim_performance": TableConfig(
        name="product_claim_performance",
        label="Claim Performance",
        group="Product Catalog",
        description="Claim settlement and performance metrics attached to products.",
        columns=["product_id", "metric_name", "metric_value", "metric_year", "metric_context", "source_note"],
        required=["product_id", "metric_name", "metric_value"],
        textarea=["metric_context", "source_note"],
        search=["metric_name", "metric_value", "metric_year", "metric_context"],
    ),
    "product_ideal_customer_profiles": TableConfig(
        name="product_ideal_customer_profiles",
        label="Ideal Customer Profiles",
        group="Product Catalog",
        description="Suitability profiles used by the chatbot for recommendations.",
        columns=[
            "product_id", "profile_summary", "customer_life_stage", "income_segment",
            "risk_profile", "recommended_for", "not_recommended_for",
        ],
        required=["product_id", "profile_summary"],
        textarea=["profile_summary"],
        arrays=["customer_life_stage", "income_segment", "risk_profile", "recommended_for", "not_recommended_for"],
        search=["profile_summary"],
    ),
    "product_versions": TableConfig(
        name="product_versions",
        label="Product Versions",
        group="Product Catalog",
        description="Version and approval history for product records.",
        columns=[
            "product_id", "version_no", "change_type", "change_summary", "changed_fields",
            "effective_from", "effective_to", "changed_by", "approved_by",
            "approval_status", "source_type", "source_reference",
        ],
        required=["product_id", "version_no", "change_type", "change_summary"],
        textarea=["change_summary"],
        json=["changed_fields"],
        numbers=["version_no"],
        dates=["effective_from", "effective_to"],
        search=["change_type", "change_summary", "approval_status", "source_reference"],
    ),
    "product_import_batches": TableConfig(
        name="product_import_batches",
        label="Product Import Batches",
        group="Product Catalog",
        description="Import batch audit trail for structured product data.",
        columns=[
            "source_document_name", "source_document_version", "source_file_url",
            "import_status", "total_companies_detected", "total_products_detected",
            "total_products_added", "total_products_updated", "total_products_removed",
            "import_notes", "created_by", "completed_at",
        ],
        required=["source_document_name"],
        textarea=["import_notes"],
        numbers=[
            "total_companies_detected", "total_products_detected", "total_products_added",
            "total_products_updated", "total_products_removed",
        ],
        dates=["completed_at"],
        search=["source_document_name", "source_document_version", "import_status", "import_notes"],
    ),
    "product_change_log": TableConfig(
        name="product_change_log",
        label="Product Change Log",
        group="Product Catalog",
        description="Field-level product change audit notes.",
        columns=["product_id", "action", "field_name", "old_value", "new_value", "performed_by", "reason"],
        required=["action"],
        textarea=["old_value", "new_value", "reason"],
        search=["action", "field_name", "old_value", "new_value", "reason"],
        order_by="performed_at",
    ),
    "law_sources": TableConfig(
        name="law_sources",
        label="Law Sources",
        group="Legal Handbook",
        description="Legal source documents, versions, and validity windows.",
        columns=[
            "source_name", "source_type", "version_label", "effective_from",
            "effective_to", "is_active", "notes",
        ],
        required=["source_name"],
        textarea=["notes"],
        booleans=["is_active"],
        dates=["effective_from", "effective_to"],
        search=["source_name", "source_type", "version_label", "notes"],
    ),
    "legal_categories": TableConfig(
        name="legal_categories",
        label="Legal Categories",
        group="Legal Handbook",
        description="High-level grouping for legal instruments and provisions.",
        columns=["category_name", "category_code", "description", "display_order", "is_active"],
        required=["category_name"],
        textarea=["description"],
        booleans=["is_active"],
        numbers=["display_order"],
        search=["category_name", "category_code", "description"],
    ),
    "legal_instruments": TableConfig(
        name="legal_instruments",
        label="Legal Instruments",
        group="Legal Handbook",
        description="Acts, rules, circulars, regulations, frameworks, and amendments.",
        columns=[
            "category_id", "instrument_name", "instrument_type", "year",
            "regulator_or_authority", "purpose", "applicability", "current_status",
            "source_id", "valid_from", "valid_to", "is_active",
        ],
        required=["instrument_name"],
        textarea=["purpose", "applicability"],
        booleans=["is_active"],
        numbers=["year"],
        dates=["valid_from", "valid_to"],
        search=["instrument_name", "instrument_type", "regulator_or_authority", "purpose", "applicability"],
    ),
    "legal_provisions": TableConfig(
        name="legal_provisions",
        label="Legal Provisions",
        group="Legal Handbook",
        description="Sections, regulations, rules, guidelines, and practical meanings.",
        columns=[
            "instrument_id", "provision_code", "provision_title", "provision_type",
            "summary", "practical_meaning", "applies_to", "is_active", "source_id",
        ],
        required=["provision_title"],
        textarea=["summary", "practical_meaning"],
        arrays=["applies_to"],
        booleans=["is_active"],
        search=["provision_code", "provision_title", "summary", "practical_meaning"],
    ),
    "regulatory_requirements": TableConfig(
        name="regulatory_requirements",
        label="Regulatory Requirements",
        group="Legal Handbook",
        description="Mandatory rules, values, deadlines, and frequencies.",
        columns=[
            "provision_id", "requirement_name", "requirement_description",
            "applicable_entity", "requirement_value", "unit", "deadline_days",
            "frequency", "is_mandatory", "is_active",
        ],
        required=["requirement_name"],
        textarea=["requirement_description"],
        booleans=["is_mandatory", "is_active"],
        numbers=["deadline_days"],
        search=["requirement_name", "requirement_description", "applicable_entity", "requirement_value"],
    ),
    "intermediary_types": TableConfig(
        name="intermediary_types",
        label="Intermediary Types",
        group="Legal Handbook",
        description="Agent, broker, POSP, and corporate-agent rule summaries.",
        columns=[
            "intermediary_name", "represents", "max_insurers", "min_qualification",
            "training_requirement", "key_compliance", "min_net_worth",
            "licence_requirement", "is_active",
        ],
        required=["intermediary_name"],
        textarea=["training_requirement", "key_compliance", "licence_requirement"],
        booleans=["is_active"],
        search=["intermediary_name", "represents", "max_insurers", "min_qualification", "key_compliance"],
    ),
    "policyholder_rights": TableConfig(
        name="policyholder_rights",
        label="Policyholder Rights",
        group="Legal Handbook",
        description="Customer rights, time limits, refunds, compensation, and escalation options.",
        columns=[
            "right_name", "right_category", "description", "applicable_insurance_type",
            "time_limit", "refund_or_compensation_rule", "escalation_available",
            "related_provision_id", "is_active",
        ],
        required=["right_name"],
        textarea=["description", "refund_or_compensation_rule"],
        arrays=["applicable_insurance_type"],
        booleans=["escalation_available", "is_active"],
        search=["right_name", "right_category", "description", "time_limit"],
    ),
    "grievance_channels": TableConfig(
        name="grievance_channels",
        label="Grievance Channels",
        group="Legal Handbook",
        description="Escalation forums and time limits for insurance complaints.",
        columns=["tier_no", "forum_name", "access_method", "time_limit", "max_compensation", "scope", "next_escalation_id", "is_active"],
        required=["forum_name"],
        textarea=["access_method", "scope"],
        booleans=["is_active"],
        numbers=["tier_no"],
        search=["forum_name", "access_method", "time_limit", "scope"],
        order_by="tier_no",
    ),
    "violation_types": TableConfig(
        name="violation_types",
        label="Violation Types",
        group="Legal Handbook",
        description="Compliance and customer-protection violation categories.",
        columns=["violation_category", "example_violation", "responsible_party", "related_provision_id", "is_active"],
        required=["violation_category"],
        textarea=["example_violation"],
        booleans=["is_active"],
        search=["violation_category", "example_violation", "responsible_party"],
    ),
    "penalties": TableConfig(
        name="penalties",
        label="Penalties",
        group="Legal Handbook",
        description="Penalty amounts, consequences, and authorities.",
        columns=["violation_type_id", "penalty_title", "penalty_description", "max_penalty_amount", "penalty_unit", "consequence", "authority", "is_active"],
        required=["penalty_title"],
        textarea=["penalty_description", "consequence"],
        booleans=["is_active"],
        numbers=["max_penalty_amount"],
        search=["penalty_title", "penalty_description", "consequence", "authority"],
    ),
    "legal_change_log": TableConfig(
        name="legal_change_log",
        label="Legal Change Log",
        group="Legal Handbook",
        description="Structured audit trail for legal table changes.",
        columns=["entity_table", "entity_id", "change_type", "old_value", "new_value", "change_reason", "effective_date", "source_reference", "changed_by"],
        required=["entity_table", "entity_id"],
        textarea=["change_reason", "source_reference"],
        json=["old_value", "new_value"],
        dates=["effective_date"],
        search=["entity_table", "change_type", "change_reason", "source_reference"],
    ),
}


def _config(table: str) -> TableConfig:
    config = TABLES.get(table)
    if not config:
        raise HTTPException(status_code=404, detail="Table is not managed by the admin data module.")
    return config


def _sanitize_payload(config: TableConfig, payload: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    allowed = set(config.columns)
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed or key in config.readonly:
            continue
        if value == "":
            value = None
        if key in config.arrays and isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        sanitized[key] = value

    missing = [field for field in config.required if not sanitized.get(field)]
    if missing and not partial:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")
    return sanitized


def _invalidate_runtime_cache(table: str) -> None:
    if table.startswith("product_") or table in {"insurance_companies", "insurance_products"}:
        clear_product_catalog_cache()
    if table.startswith("legal_") or table in {
        "law_sources", "regulatory_requirements", "intermediary_types",
        "policyholder_rights", "grievance_channels", "violation_types", "penalties",
    }:
        clear_legal_cache()


@router.get("/tables")
async def list_managed_tables():
    grouped: dict[str, list[dict[str, Any]]] = {}
    for config in TABLES.values():
        grouped.setdefault(config.group, []).append(config.model_dump())
    return {"groups": grouped, "tables": [config.model_dump() for config in TABLES.values()]}


@router.get("/{table}")
async def list_rows(
    table: str,
    q: str = "",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    config = _config(table)
    db = get_db()
    query = db.table(table).select("*", count="exact")
    if q.strip() and config.search:
        term = q.strip().replace("%", "\\%").replace(",", " ")
        filters = ",".join(f"{column}.ilike.%{term}%" for column in config.search)
        query = query.or_(filters)
    try:
        response = (
            query
            .order(config.order_by, desc=config.order_by != "tier_no")
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load {table}: {exc}") from exc

    return {
        "table": config.model_dump(),
        "rows": response.data or [],
        "count": response.count or 0,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{table}")
async def create_row(table: str, payload: RowPayload):
    config = _config(table)
    data = _sanitize_payload(config, payload.data)
    try:
        response = get_db().table(table).insert(data).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create row in {table}: {exc}") from exc
    _invalidate_runtime_cache(table)
    return {"row": (response.data or [None])[0]}


@router.patch("/{table}/{row_id}")
async def update_row(table: str, row_id: str, payload: RowPayload):
    config = _config(table)
    data = _sanitize_payload(config, payload.data, partial=True)
    if not data:
        raise HTTPException(status_code=422, detail="No editable fields were provided.")
    try:
        response = get_db().table(table).update(data).eq("id", row_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update row in {table}: {exc}") from exc
    _invalidate_runtime_cache(table)
    return {"row": (response.data or [None])[0]}


@router.delete("/{table}/{row_id}")
async def delete_row(table: str, row_id: str):
    _config(table)
    try:
        response = get_db().table(table).delete().eq("id", row_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete row from {table}: {exc}") from exc
    _invalidate_runtime_cache(table)
    return {"deleted": bool(response.data), "row": (response.data or [None])[0]}

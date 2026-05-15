"""
Structured product catalog lookup and validation.

This service treats the Supabase product tables as the source of truth for
product-to-insurer attribution, eligibility, features, benefits, riders, and
conditions. It is intentionally lightweight: the imported catalog is small, so
we cache it in-process and rank locally for low latency.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.db import get_db


CACHE_TTL_SECONDS = 300
PRODUCT_INTENT_TERMS = {
    "insurance", "policy", "plan", "product", "mediclaim", "health", "term",
    "life", "ulip", "endowment", "rider", "addon", "add-on", "cover",
    "coverage", "floater", "senior", "citizen", "premium", "sum", "assured",
    "motor", "car", "two-wheeler", "buy", "recommend", "eligibility",
}
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "they", "their", "can",
    "will", "what", "which", "should", "want", "wants", "have", "has",
    "about", "from", "into", "your", "ours", "his", "her", "its", "are",
}
CATEGORY_ALIASES = {
    "health": {"health", "mediclaim", "medical", "hospital", "senior", "citizen", "floater"},
    "life": {"life", "term", "ulip", "endowment", "annuity", "retirement", "pension"},
    "motor": {"motor", "car", "vehicle", "two", "wheeler", "bike", "od", "tp"},
    "travel": {"travel", "trip", "overseas"},
    "home": {"home", "house", "property"},
    "commercial": {"commercial", "business", "liability", "sme"},
    "reinsurance": {"reinsurance", "reinsurer"},
}
LIST_INTENT_TERMS = {"all", "list", "show", "companies", "company", "insurers", "insurer", "products", "product", "catalog", "database", "know"}
DETAIL_INTENT_TERMS = {"compare", "best", "recommend", "suitable", "eligibility", "cover", "coverage", "premium", "waiting", "claim", "benefit", "feature", "condition", "rider", "addon", "add-on"}


@dataclass
class CatalogCache:
    loaded_at: float = 0.0
    companies: dict[str, dict[str, Any]] = field(default_factory=dict)
    products: list[dict[str, Any]] = field(default_factory=list)
    features: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    benefits: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    conditions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    riders: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    claim_performance: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    profiles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


_cache = CatalogCache()


def clear_product_catalog_cache() -> None:
    global _cache
    _cache = CatalogCache()


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalize(text).split()
        if len(token) >= 3 and token not in STOPWORDS
    }


def _combined_query(query: str, evidence_text: str = "") -> str:
    return "\n".join(part for part in [query or "", evidence_text or ""] if part).strip()


def _group_by_product(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        product_id = str(row.get("product_id") or "")
        if product_id:
            grouped.setdefault(product_id, []).append(row)
    return grouped


def _load_catalog() -> CatalogCache:
    now = time.time()
    if _cache.loaded_at and now - _cache.loaded_at < CACHE_TTL_SECONDS:
        return _cache

    db = get_db()
    companies = (
        db.table("insurance_companies")
        .select("*")
        .eq("status", "active")
        .execute()
        .data
        or []
    )
    company_by_id = {str(company["id"]): company for company in companies}

    products = (
        db.table("insurance_products")
        .select("*")
        .eq("current_status", "active")
        .execute()
        .data
        or []
    )
    for product in products:
        product["company"] = company_by_id.get(str(product.get("company_id")), {})
        product["_search_text"] = _normalize(
            " ".join(
                [
                    product.get("product_name") or "",
                    product.get("product_slug") or "",
                    product.get("plan_code") or "",
                    product.get("product_category") or "",
                    product.get("product_type") or "",
                    product.get("eligibility_summary") or "",
                    product.get("short_description") or "",
                    product["company"].get("company_name") or "",
                    product["company"].get("company_slug") or "",
                ]
            )
        )
        product["_tokens"] = _tokens(product["_search_text"])

    product_ids = [product["id"] for product in products]
    def child(table: str) -> list[dict[str, Any]]:
        if not product_ids:
            return []
        return db.table(table).select("*").in_("product_id", product_ids).execute().data or []

    _cache.loaded_at = now
    _cache.companies = company_by_id
    _cache.products = products
    _cache.features = _group_by_product(child("product_features"))
    _cache.benefits = _group_by_product(child("product_benefits"))
    _cache.conditions = _group_by_product(child("product_conditions"))
    _cache.riders = _group_by_product(child("product_riders_addons"))
    _cache.claim_performance = _group_by_product(child("product_claim_performance"))
    _cache.profiles = _group_by_product(child("product_ideal_customer_profiles"))
    return _cache


def should_use_product_catalog(query: str) -> bool:
    query_tokens = _tokens(query)
    if query_tokens.intersection(PRODUCT_INTENT_TERMS):
        return True
    normalized = _normalize(query)
    return any(
        term in normalized
        for term in ["red carpet", "click 2 protect", "tech term", "optima secure", "reassure", "iprotect"]
    )


def _requested_categories(text: str) -> set[str]:
    tokens = _tokens(text)
    categories = {
        category
        for category, aliases in CATEGORY_ALIASES.items()
        if tokens.intersection(aliases)
    }
    normalized = _normalize(text)
    for category in CATEGORY_ALIASES:
        if category in normalized:
            categories.add(category)
    return categories


def _is_catalog_list_query(text: str) -> bool:
    tokens = _tokens(text)
    has_list_intent = bool(tokens.intersection(LIST_INTENT_TERMS))
    has_catalog_subject = bool(tokens.intersection(PRODUCT_INTENT_TERMS)) or bool(_requested_categories(text))
    return has_list_intent and has_catalog_subject


def _score_product(query: str, product: dict[str, Any], evidence_text: str = "") -> float:
    combined = _combined_query(query, evidence_text)
    normalized_query = _normalize(combined)
    query_tokens = _tokens(combined)
    product_name = _normalize(product.get("product_name") or "")
    company_name = _normalize((product.get("company") or {}).get("company_name") or "")

    score = 0.0
    if product_name and product_name in normalized_query:
        score += 7.0
    if company_name and company_name in normalized_query:
        score += 3.0

    overlap = query_tokens.intersection(product.get("_tokens") or set())
    score += min(len(overlap) * 0.7, 4.2)

    category = product.get("product_category") or ""
    product_type = product.get("product_type") or ""
    category_text = _normalize(f"{category} {product_type}")
    requested_categories = _requested_categories(combined)
    if requested_categories and category in requested_categories:
        score += 2.5
    if "senior" in normalized_query and "senior" in category_text:
        score += 2.0
    if "mediclaim" in normalized_query and "health" in category_text:
        score += 1.5
    if "floater" in normalized_query and "floater" in category_text:
        score += 1.5
    if "term" in normalized_query and "term" in category_text:
        score += 1.5
    if "motor" in normalized_query or "car" in normalized_query:
        if "motor" in category_text or "car" in product_name:
            score += 1.5
    return score


def search_products(query: str, evidence_text: str = "", limit: int = 5) -> list[dict[str, Any]]:
    combined = _combined_query(query, evidence_text)
    if not should_use_product_catalog(combined):
        return []
    catalog = _load_catalog()
    scored = [
        (product, _score_product(query, product, evidence_text=evidence_text))
        for product in catalog.products
    ]
    ranked = [
        product
        for product, score in sorted(scored, key=lambda item: item[1], reverse=True)
        if score >= 1.4
    ]
    return ranked[:limit]


def _short_list(rows: list[dict[str, Any]], key: str, limit: int = 4) -> list[str]:
    values = []
    for row in rows[:limit]:
        value = row.get(key)
        if value:
            values.append(str(value))
    return values


def _catalog_products(catalog: CatalogCache, categories: set[str]) -> list[dict[str, Any]]:
    products = catalog.products
    if categories:
        products = [
            product
            for product in products
            if (product.get("product_category") or "").lower() in categories
        ]
    return sorted(
        products,
        key=lambda product: (
            ((product.get("company") or {}).get("company_name") or "").lower(),
            (product.get("product_name") or "").lower(),
        ),
    )


def _build_catalog_list(query: str, evidence_text: str = "") -> dict[str, Any]:
    catalog = _load_catalog()
    combined = _combined_query(query, evidence_text)
    categories = _requested_categories(combined)
    products = _catalog_products(catalog, categories)
    if not products:
        return {"context": "", "citations": [], "products": [], "deterministic_answer": ""}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        company_name = (product.get("company") or {}).get("company_name") or "Unknown insurer"
        grouped.setdefault(company_name, []).append(product)

    answer_lines = [
        "From the structured product catalog currently imported, these are the insurance companies and products I know"
        + (f" for {', '.join(sorted(categories))} insurance:" if categories else ":"),
        "",
    ]
    context_lines = [
        "STRUCTURED PRODUCT CATALOG FACTS (authoritative):",
        "The user asked for an insurance company/product inventory. Use ONLY the products listed below. Do not add generic products, companies, insurers, or categories that are not present in the structured catalog.",
    ]

    for company_name, company_products in grouped.items():
        answer_lines.append(f"{company_name}:")
        context_lines.append(f"Insurer: {company_name}")
        for product in company_products:
            product_line = f"- {product.get('product_name')} ({product.get('product_category') or 'insurance'} / {product.get('product_type') or 'product'})"
            if product.get("eligibility_summary"):
                product_line += f" | Eligibility: {product.get('eligibility_summary')}"
            answer_lines.append(product_line)
            context_lines.append(
                f"Product: {product.get('product_name')} | Category/type: {product.get('product_category') or 'insurance'} / {product.get('product_type') or 'product'} | "
                f"Eligibility: {product.get('eligibility_summary') or 'Not specified'}"
            )
        answer_lines.append("")
        context_lines.append("")

    answer_lines.append(
        "I have listed only products present in the structured catalog. Please verify final premium, coverage, waiting periods, exclusions, and eligibility from the official policy brochure before purchase."
    )

    citations = []
    for product in products[:12]:
        company_name = (product.get("company") or {}).get("company_name") or "Unknown insurer"
        preview = f"{product.get('product_name')} by {company_name}: {product.get('eligibility_summary') or product.get('product_type') or ''}"
        citations.append(
            {
                "chunk_id": f"product:{product.get('id')}",
                "document_id": str(product.get("id")),
                "document_title": "Structured Product Catalog",
                "page_start": None,
                "page_end": None,
                "section_title": product.get("product_name"),
                "page_number": None,
                "chunk_preview": preview[:240],
                "relevance_score": 1.0,
            }
        )

    enriched_products = []
    for product in products:
        product_id = str(product["id"])
        enriched_products.append(
            {
                **product,
                "features": catalog.features.get(product_id, []),
                "benefits": catalog.benefits.get(product_id, []),
                "conditions": catalog.conditions.get(product_id, []),
                "riders": catalog.riders.get(product_id, []),
                "claim_performance": catalog.claim_performance.get(product_id, []),
                "profiles": catalog.profiles.get(product_id, []),
            }
        )

    return {
        "context": "\n".join(context_lines).strip(),
        "citations": citations,
        "products": enriched_products,
        "deterministic_answer": "\n".join(answer_lines).strip(),
    }


def build_product_context(query: str, evidence_text: str = "", limit: int = 6) -> dict[str, Any]:
    combined = _combined_query(query, evidence_text)
    if _is_catalog_list_query(combined):
        return _build_catalog_list(query, evidence_text=evidence_text)

    products = search_products(query, evidence_text=evidence_text, limit=limit)
    if not products:
        return {"context": "", "citations": [], "products": [], "deterministic_answer": ""}

    catalog = _load_catalog()
    sections = ["STRUCTURED PRODUCT CATALOG FACTS (authoritative):"]
    citations = []
    enriched_products = []

    for product in products:
        product_id = str(product["id"])
        company = product.get("company") or {}
        features = catalog.features.get(product_id, [])
        benefits = catalog.benefits.get(product_id, [])
        conditions = catalog.conditions.get(product_id, [])
        riders = catalog.riders.get(product_id, [])
        claim_rows = catalog.claim_performance.get(product_id, [])
        profile_rows = catalog.profiles.get(product_id, [])

        section_lines = [
            f"Product: {product.get('product_name')}",
            f"Insurer: {company.get('company_name')}",
            f"Category/type: {product.get('product_category')} / {product.get('product_type')}",
            f"Eligibility: {product.get('eligibility_summary') or 'Not specified'}",
            f"Policy term: {product.get('policy_term') or 'Not specified'}",
            f"Premium payment term: {product.get('premium_payment_term') or 'Not specified'}",
            f"Sum assured range: {product.get('min_sum_assured') or 'N/A'} to {product.get('max_sum_assured') or 'N/A'}",
            f"Premium range: {product.get('premium_range') or 'Not specified'}",
        ]
        if features:
            section_lines.append("Key features: " + "; ".join(_short_list(features, "feature_description")))
        if benefits:
            section_lines.append("Benefits: " + "; ".join(_short_list(benefits, "benefit_description")))
        if conditions:
            section_lines.append("Conditions/exclusions: " + "; ".join(_short_list(conditions, "condition_description")))
        if riders:
            section_lines.append("Riders/add-ons: " + "; ".join(_short_list(riders, "rider_name")))
        if claim_rows:
            section_lines.append("Claim/performance: " + "; ".join(_short_list(claim_rows, "metric_context")))
        if profile_rows:
            section_lines.append("Ideal profile: " + "; ".join(_short_list(profile_rows, "profile_summary", limit=2)))
        section_lines.append(
            "Important: do not infer coverage for adult children/spouses in this product unless the fields above explicitly say so."
        )

        sections.append("\n".join(section_lines))
        preview = f"{product.get('product_name')} by {company.get('company_name')}: {product.get('eligibility_summary') or product.get('product_type') or ''}"
        citations.append(
            {
                "chunk_id": f"product:{product.get('id')}",
                "document_id": str(product.get("id")),
                "document_title": "Structured Product Catalog",
                "page_start": None,
                "page_end": None,
                "section_title": product.get("product_name"),
                "page_number": None,
                "chunk_preview": preview[:240],
                "relevance_score": 1.0,
            }
        )
        enriched_products.append(
            {
                **product,
                "features": features,
                "benefits": benefits,
                "conditions": conditions,
                "riders": riders,
                "claim_performance": claim_rows,
                "profiles": profile_rows,
            }
        )

    return {
        "context": "\n\n".join(sections),
        "citations": citations,
        "products": enriched_products,
        "deterministic_answer": "",
    }


def validate_product_attributions(answer: str, products: list[dict[str, Any]] | None = None) -> str:
    if not answer:
        return answer
    if products is None:
        products = _load_catalog().products

    corrected = answer
    for product in products:
        product_name = product.get("product_name") or ""
        company_name = (product.get("company") or {}).get("company_name") or ""
        if not product_name or not company_name:
            continue

        escaped_product = re.escape(product_name)
        pattern = re.compile(
            rf"\b(?P<product>{escaped_product})\s+"
            rf"(?P<link>by|from|of|issued by|offered by|provided by)\s+"
            rf"(?P<insurer>[A-Z][A-Za-z&.\s]{{2,80}})",
            flags=re.IGNORECASE,
        )

        def replace(match: re.Match[str]) -> str:
            insurer = match.group("insurer").strip(" .,:;")
            if _normalize(company_name) in _normalize(insurer) or _normalize(insurer) in _normalize(company_name):
                return match.group(0)
            return f"{product_name} by {company_name}"

        corrected = pattern.sub(replace, corrected)
    return corrected

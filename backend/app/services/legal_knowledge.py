"""
Structured legal handbook lookup.

Uses the legal/handbook Supabase tables as a deterministic supplement to RAG.
The data is small, so local cached ranking is faster and more predictable than
round-tripping many fuzzy database queries.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.db import get_db


CACHE_TTL_SECONDS = 300
LEGAL_INTENT_TERMS = {
    "irdai", "section", "act", "law", "legal", "regulation", "rule",
    "compliance", "free-look", "freelook", "ombudsman", "bima", "bharosa",
    "grievance", "complaint", "mis-selling", "misselling", "penalty",
    "claim", "rejection", "moratorium", "disclosure", "agent", "broker",
    "policyholder", "right", "rights", "solvency", "fdi",
}
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "they", "their", "can",
    "will", "what", "which", "should", "want", "wants", "have", "has",
    "about", "from", "into", "your", "ours", "his", "her", "its", "are",
}


@dataclass
class LegalCache:
    loaded_at: float = 0.0
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    provisions: list[dict[str, Any]] = field(default_factory=list)
    requirements: list[dict[str, Any]] = field(default_factory=list)
    rights: list[dict[str, Any]] = field(default_factory=list)
    grievances: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    penalties: list[dict[str, Any]] = field(default_factory=list)


_cache = LegalCache()


def clear_legal_cache() -> None:
    global _cache
    _cache = LegalCache()


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


def should_use_legal_knowledge(query: str) -> bool:
    normalized = _normalize(query)
    tokens = _tokens(query)
    return bool(tokens.intersection(LEGAL_INTENT_TERMS)) or any(
        phrase in normalized
        for phrase in ["free look", "bima bharosa", "claim rejected", "claim rejection", "section 45"]
    )


def _load_legal() -> LegalCache:
    now = time.time()
    if _cache.loaded_at and now - _cache.loaded_at < CACHE_TTL_SECONDS:
        return _cache

    db = get_db()
    sources = db.table("law_sources").select("*").eq("is_active", True).execute().data or []
    instruments = db.table("legal_instruments").select("*").eq("is_active", True).execute().data or []
    provisions = db.table("legal_provisions").select("*").eq("is_active", True).execute().data or []
    requirements = db.table("regulatory_requirements").select("*").eq("is_active", True).execute().data or []
    rights = db.table("policyholder_rights").select("*").eq("is_active", True).execute().data or []
    grievances = db.table("grievance_channels").select("*").eq("is_active", True).order("tier_no").execute().data or []
    violations = db.table("violation_types").select("*").eq("is_active", True).execute().data or []
    penalties = db.table("penalties").select("*").eq("is_active", True).execute().data or []

    source_by_id = {str(source["id"]): source for source in sources}
    instrument_by_id = {str(instrument["id"]): instrument for instrument in instruments}

    for provision in provisions:
        instrument = instrument_by_id.get(str(provision.get("instrument_id")), {})
        source = source_by_id.get(str(provision.get("source_id")), {})
        provision["instrument"] = instrument
        provision["source"] = source
        provision["_tokens"] = _tokens(
            " ".join(
                [
                    provision.get("provision_code") or "",
                    provision.get("provision_title") or "",
                    provision.get("summary") or "",
                    provision.get("practical_meaning") or "",
                    " ".join(provision.get("applies_to") or []),
                    instrument.get("instrument_name") or "",
                ]
            )
        )

    for requirement in requirements:
        requirement["_tokens"] = _tokens(
            " ".join(
                [
                    requirement.get("requirement_name") or "",
                    requirement.get("requirement_description") or "",
                    requirement.get("applicable_entity") or "",
                    requirement.get("requirement_value") or "",
                ]
            )
        )

    for right in rights:
        right["_tokens"] = _tokens(
            " ".join(
                [
                    right.get("right_name") or "",
                    right.get("right_category") or "",
                    right.get("description") or "",
                    right.get("time_limit") or "",
                    right.get("refund_or_compensation_rule") or "",
                    " ".join(right.get("applicable_insurance_type") or []),
                ]
            )
        )

    _cache.loaded_at = now
    _cache.sources = source_by_id
    _cache.instruments = instrument_by_id
    _cache.provisions = provisions
    _cache.requirements = requirements
    _cache.rights = rights
    _cache.grievances = grievances
    _cache.violations = violations
    _cache.penalties = penalties
    return _cache


def _rank(rows: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    scored = []
    normalized = _normalize(query)
    for row in rows:
        tokens = row.get("_tokens") or set()
        score = len(query_tokens.intersection(tokens)) * 0.8
        for key in ["provision_code", "provision_title", "right_name", "requirement_name"]:
            value = _normalize(str(row.get(key) or ""))
            if value and value in normalized:
                score += 4.0
        if score >= 0.8:
            scored.append((row, score))
    return [row for row, _ in sorted(scored, key=lambda item: item[1], reverse=True)[:limit]]


def build_legal_context(query: str, evidence_text: str = "", limit: int = 4) -> dict[str, Any]:
    combined = _combined_query(query, evidence_text)
    if not should_use_legal_knowledge(combined):
        return {"context": "", "citations": []}

    cache = _load_legal()
    provisions = _rank(cache.provisions, combined, limit=limit)
    requirements = _rank(cache.requirements, combined, limit=3)
    rights = _rank(cache.rights, combined, limit=3)

    normalized = _normalize(combined)
    include_grievance = any(term in normalized for term in ["grievance", "complaint", "ombudsman", "bima bharosa", "claim rejection", "rejected"])

    sections = ["STRUCTURED LEGAL / HANDBOOK FACTS (authoritative):"]
    citations = []

    for provision in provisions:
        instrument = provision.get("instrument") or {}
        lines = [
            f"Provision: {provision.get('provision_code')} - {provision.get('provision_title')}",
            f"Instrument: {instrument.get('instrument_name')}",
            f"Summary: {provision.get('summary')}",
            f"Practical meaning: {provision.get('practical_meaning')}",
            f"Applies to: {', '.join(provision.get('applies_to') or [])}",
        ]
        sections.append("\n".join(line for line in lines if line and not line.endswith("None")))
        citations.append(
            {
                "chunk_id": f"legal_provision:{provision.get('id')}",
                "document_id": str(provision.get("id")),
                "document_title": "Structured Legal Handbook",
                "page_start": None,
                "page_end": None,
                "section_title": f"{provision.get('provision_code')} {provision.get('provision_title')}",
                "page_number": None,
                "chunk_preview": (provision.get("summary") or provision.get("practical_meaning") or "")[:240],
                "relevance_score": 1.0,
            }
        )

    for requirement in requirements:
        sections.append(
            "\n".join(
                [
                    f"Regulatory requirement: {requirement.get('requirement_name')}",
                    f"Description: {requirement.get('requirement_description')}",
                    f"Applies to: {requirement.get('applicable_entity')}",
                    f"Value/deadline: {requirement.get('requirement_value') or 'N/A'} {requirement.get('unit') or ''}; {requirement.get('frequency') or ''}",
                ]
            )
        )
        citations.append(
            {
                "chunk_id": f"legal_requirement:{requirement.get('id')}",
                "document_id": str(requirement.get("id")),
                "document_title": "Structured Legal Handbook",
                "page_start": None,
                "page_end": None,
                "section_title": requirement.get("requirement_name"),
                "page_number": None,
                "chunk_preview": (requirement.get("requirement_description") or "")[:240],
                "relevance_score": 1.0,
            }
        )

    for right in rights:
        sections.append(
            "\n".join(
                [
                    f"Policyholder right: {right.get('right_name')}",
                    f"Category: {right.get('right_category')}",
                    f"Description: {right.get('description')}",
                    f"Time limit: {right.get('time_limit')}",
                    f"Refund/compensation: {right.get('refund_or_compensation_rule')}",
                ]
            )
        )
        citations.append(
            {
                "chunk_id": f"policyholder_right:{right.get('id')}",
                "document_id": str(right.get("id")),
                "document_title": "Structured Legal Handbook",
                "page_start": None,
                "page_end": None,
                "section_title": right.get("right_name"),
                "page_number": None,
                "chunk_preview": (right.get("description") or "")[:240],
                "relevance_score": 1.0,
            }
        )

    if include_grievance and cache.grievances:
        grievance_lines = ["Grievance escalation path:"]
        for row in cache.grievances[:5]:
            grievance_lines.append(
                f"Tier {row.get('tier_no')}: {row.get('forum_name')} - {row.get('access_method')} "
                f"(time limit: {row.get('time_limit')})"
            )
        sections.append("\n".join(grievance_lines))
        citations.append(
            {
                "chunk_id": "legal_grievance_channels",
                "document_id": "legal_grievance_channels",
                "document_title": "Structured Legal Handbook",
                "page_start": None,
                "page_end": None,
                "section_title": "Grievance channels",
                "page_number": None,
                "chunk_preview": "GRO, Bima Bharosa, Ombudsman, Consumer Forum escalation path.",
                "relevance_score": 1.0,
            }
        )

    if len(sections) == 1:
        return {"context": "", "citations": []}
    return {"context": "\n\n".join(sections), "citations": citations[:8]}

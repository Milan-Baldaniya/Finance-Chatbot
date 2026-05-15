"""
Combines structured product and legal knowledge for chat generation.
"""

from __future__ import annotations

import logging

from app.services.legal_knowledge import build_legal_context
from app.services.product_catalog_db import build_product_context, validate_product_attributions

logger = logging.getLogger(__name__)


def _chunk_text(chunk: dict) -> str:
    return chunk.get("chunk_text", chunk.get("content", "")) or ""


def _evidence_text_from_chunks(chunks: list[dict] | None, max_chars: int = 6000) -> str:
    if not chunks:
        return ""
    parts = []
    for chunk in chunks[:8]:
        parts.append(
            " ".join(
                str(value)
                for value in [
                    chunk.get("document_title"),
                    chunk.get("section_title"),
                    _chunk_text(chunk),
                ]
                if value
            )
        )
    return "\n".join(parts)[:max_chars]


def build_structured_context(query: str, evidence_chunks: list[dict] | None = None) -> dict:
    evidence_text = _evidence_text_from_chunks(evidence_chunks)

    try:
        product = build_product_context(query, evidence_text=evidence_text)
    except Exception as exc:
        logger.error("Structured product catalog lookup failed: %s", exc)
        product = {"context": "", "citations": [], "products": [], "deterministic_answer": ""}

    try:
        legal = build_legal_context(query, evidence_text=evidence_text)
    except Exception as exc:
        logger.error("Structured legal lookup failed: %s", exc)
        legal = {"context": "", "citations": []}

    context_parts = [
        part for part in [product.get("context"), legal.get("context")] if part
    ]
    citations = [*(product.get("citations") or []), *(legal.get("citations") or [])]
    products = product.get("products") or []

    return {
        "context": "\n\n".join(context_parts),
        "citations": citations[:10],
        "products": products,
        "deterministic_answer": product.get("deterministic_answer") or "",
    }


def validate_structured_answer(answer: str, structured_context: dict) -> str:
    corrected = validate_product_attributions(answer, structured_context.get("products") or None)
    return corrected

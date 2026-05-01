"""
Retrieval service for Phase 4/5 runtime flow.
"""

import logging
from typing import Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.db import get_db
from app.services.embeddings import generate_embeddings
from app.services.llm import expand_query


settings = get_settings()
logger = logging.getLogger(__name__)


def classify_intent(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["claim", "settlement", "cashless", "reimbursement"]):
        return "claims"
    if any(k in q for k in ["exclusion", "not covered", "waiting period", "coverage"]):
        return "exclusions"
    if any(k in q for k in ["regulation", "irda", "compliance", "legal"]):
        return "regulatory"
    return "general"


def source_group_filter_for_intent(intent: str) -> Optional[str]:
    mapping = {
        "exclusions": "policy_wordings",
        "claims": "claim_docs",
        "regulatory": "compliance_docs",
    }
    return mapping.get(intent)


def should_rewrite_query(query: str, history: List[Dict]) -> bool:
    words = [w for w in query.strip().split() if w]
    short_query = len(words) <= 6
    follow_up_markers = {"this", "that", "it", "they", "these", "those", "above", "same"}
    follow_up = bool(history) and any(w.lower().strip("?.!,") in follow_up_markers for w in words)
    return short_query or follow_up


def _vector_search(
    query_embedding: List[float],
    match_count: int,
    similarity_threshold: float,
    source_group_filter: Optional[str] = None,
    document_id_filter: Optional[str] = None,
) -> List[Dict]:
    db = get_db()
    response = db.rpc(
        "match_document_chunks",
        {
            "query_embedding": query_embedding,
            "match_count": match_count,
            "similarity_threshold": similarity_threshold,
            "source_group_filter": source_group_filter,
            "document_id_filter": document_id_filter,
        },
    ).execute()
    return response.data or []


def _keyword_search(
    query_text: str,
    match_count: int,
    source_group_filter: Optional[str] = None,
    document_id_filter: Optional[str] = None,
) -> List[Dict]:
    db = get_db()
    response = db.rpc(
        "keyword_match_document_chunks",
        {
            "query_text": query_text,
            "match_count": match_count,
            "source_group_filter": source_group_filter,
            "document_id_filter": document_id_filter,
        },
    ).execute()
    return response.data or []


def _normalize_scores(chunks: List[Dict], key: str) -> Dict[str, float]:
    if not chunks:
        return {}
    values = [float(chunk.get(key, 0.0) or 0.0) for chunk in chunks]
    min_v = min(values)
    max_v = max(values)
    scores = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id"))
        raw = float(chunk.get(key, 0.0) or 0.0)
        if max_v == min_v:
            scores[chunk_id] = 1.0 if raw > 0 else 0.0
        else:
            scores[chunk_id] = (raw - min_v) / (max_v - min_v)
    return scores


def _heuristic_rerank(chunks: List[Dict], query: str, preferred_group: Optional[str]) -> List[Dict]:
    q_words = {w.lower().strip(".,?!:;()[]{}") for w in query.split() if len(w.strip()) >= 3}
    for chunk in chunks:
        text = (chunk.get("chunk_text") or "").lower()
        section = (chunk.get("section_title") or "").lower()
        overlap = sum(1 for w in q_words if w in text)
        section_bonus = 1.0 if any(w in section for w in q_words) else 0.0
        group_bonus = 1.0 if preferred_group and chunk.get("source_group") == preferred_group else 0.0
        chunk["_rerank_score"] = float(chunk.get("blended_score", chunk.get("similarity", 0.0))) + (0.03 * overlap) + (0.05 * section_bonus) + (0.05 * group_bonus)
    return sorted(chunks, key=lambda c: c.get("_rerank_score", 0.0), reverse=True)


def retrieve_context(
    query: str,
    history: List[Dict],
    document_id_filter: Optional[str] = None,
) -> Dict:
    intent = classify_intent(query)
    source_group_filter = source_group_filter_for_intent(intent)
    rewritten_query = expand_query(query, history) if should_rewrite_query(query, history) else query

    vectors = generate_embeddings([rewritten_query])
    if not vectors:
        return {
            "intent": intent,
            "rewritten_query": rewritten_query,
            "filters": {"source_group_filter": source_group_filter, "document_id_filter": document_id_filter},
            "vector_hits": [],
            "keyword_hits": [],
            "final_chunks": [],
            "error": "embedding_failed",
        }
    query_embedding = vectors[0]

    try:
        vector_hits = _vector_search(
            query_embedding=query_embedding,
            match_count=settings.rag_retrieval_candidates,
            similarity_threshold=settings.rag_similarity_threshold,
            source_group_filter=source_group_filter,
            document_id_filter=document_id_filter,
        )
    except Exception as exc:
        logger.exception("Vector search failed for query '%s': %s", rewritten_query, exc)
        return {
            "intent": intent,
            "rewritten_query": rewritten_query,
            "filters": {"source_group_filter": source_group_filter, "document_id_filter": document_id_filter},
            "vector_hits": [],
            "keyword_hits": [],
            "final_chunks": [],
            "error": "vector_search_failed",
        }

    keyword_hits: List[Dict] = []
    merged = {str(c["chunk_id"]): c for c in vector_hits}
    if settings.enable_hybrid_search:
        try:
            keyword_hits = _keyword_search(
                query_text=rewritten_query,
                match_count=settings.rag_retrieval_candidates,
                source_group_filter=source_group_filter,
                document_id_filter=document_id_filter,
            )
        except Exception as exc:
            logger.exception("Keyword search failed for query '%s': %s", rewritten_query, exc)
            keyword_hits = []

        for row in keyword_hits:
            merged.setdefault(str(row["chunk_id"]), row)

        sem_norm = _normalize_scores(vector_hits, "similarity")
        key_norm = _normalize_scores(keyword_hits, "keyword_score")
        for chunk_id, chunk in merged.items():
            chunk["semantic_score_norm"] = sem_norm.get(chunk_id, 0.0)
            chunk["keyword_score_norm"] = key_norm.get(chunk_id, 0.0)
            chunk["blended_score"] = (0.7 * sem_norm.get(chunk_id, 0.0)) + (0.3 * key_norm.get(chunk_id, 0.0))
            chunk["retrieval_confidence"] = max(
                float(chunk.get("similarity", 0.0) or 0.0),
                chunk["keyword_score_norm"],
            )
        ranked = sorted(merged.values(), key=lambda c: c.get("blended_score", 0.0), reverse=True)[:8]
    else:
        for chunk in vector_hits:
            chunk["retrieval_confidence"] = float(chunk.get("similarity", 0.0) or 0.0)
        ranked = vector_hits[:8]

    if settings.enable_reranking:
        ranked = _heuristic_rerank(ranked, rewritten_query, source_group_filter)

    final_chunks = ranked[: settings.rag_top_k]

    return {
        "intent": intent,
        "rewritten_query": rewritten_query,
        "filters": {"source_group_filter": source_group_filter, "document_id_filter": document_id_filter},
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
        "final_chunks": final_chunks,
        "error": None,
    }


def confidence_for_chunks(chunks: List[Dict]) -> float:
    if not chunks:
        return 0.0
    return max(
        float(
            chunk.get(
                "retrieval_confidence",
                chunk.get("blended_score", chunk.get("similarity", 0.0)),
            )
            or 0.0
        )
        for chunk in chunks
    )

"""
Database operations for Documents and Chunks via Supabase.
"""

from app.core.db import get_db
from app.schemas.chat import DocumentInfo, DocumentStatusSummary
from typing import Any, Dict, List, Optional
from datetime import datetime


ALLOWED_DOCUMENT_STATUSES = {
    "uploaded",
    "processing",
    "processed",
    "processed_with_warnings",
    "failed_extraction",
    "needs_ocr",
    "embedding_pending",
    "embedding_failed",
}

def _count_embedded_chunks(db, document_id: str) -> int:
    response = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .not_.is_("embedding", "null")
        .execute()
    )
    return response.count or 0

def _count_total_chunks(db, document_id: str) -> int:
    response = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .execute()
    )
    return response.count or 0


def _count_all_chunks(db) -> int:
    response = db.table("document_chunks").select("id", count="exact").execute()
    return response.count or 0


def _count_all_embedded_chunks(db) -> int:
    response = (
        db.table("document_chunks")
        .select("id", count="exact")
        .not_.is_("embedding", "null")
        .execute()
    )
    return response.count or 0

def get_all_documents() -> List[DocumentInfo]:
    """Retrieve document registry rows from Supabase."""
    try:
        db = get_db()
        response = db.table("documents").select(
            "id, title, file_name, source_group, status, total_pages, total_chunks, uploaded_at, processed_at"
        ).order("uploaded_at", desc=True).execute()

        docs = []
        for row in response.data:
            embedded_chunks = _count_embedded_chunks(db, str(row["id"]))
            docs.append(DocumentInfo(
                id=str(row["id"]),
                title=row["title"],
                file_name=row["file_name"],
                source_group=row.get("source_group"),
                status=row["status"],
                total_pages=row.get("total_pages", 0),
                total_chunks=row.get("total_chunks", 0),
                embedded_chunks=embedded_chunks,
                uploaded_at=row["uploaded_at"],
                processed_at=row.get("processed_at"),
            ))
        return docs
    except Exception as e:
        print(f"Error fetching documents: {e}")
        return []


def get_document_by_id(document_id: str) -> Optional[DocumentInfo]:
    """Fetch one document registry row with computed embedding count."""
    try:
        db = get_db()
        response = (
            db.table("documents")
            .select("id, title, file_name, source_group, domain, status, total_pages, total_chunks, uploaded_at, processed_at")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None

        row = response.data[0]
        embedded_chunks = _count_embedded_chunks(db, str(row["id"]))
        return DocumentInfo(
            id=str(row["id"]),
            title=row["title"],
            file_name=row["file_name"],
            source_group=row.get("source_group"),
            status=row["status"],
            total_pages=row.get("total_pages", 0),
            total_chunks=row.get("total_chunks", 0),
            embedded_chunks=embedded_chunks,
            uploaded_at=row["uploaded_at"],
            processed_at=row.get("processed_at"),
        )
    except Exception as e:
        print(f"Error fetching document '{document_id}': {e}")
        return None


def get_document_status_summary() -> DocumentStatusSummary:
    """Return aggregated status information for the document registry."""
    try:
        db = get_db()
        response = db.table("documents").select("status").execute()
        rows = response.data or []

        status_breakdown = {status: 0 for status in sorted(ALLOWED_DOCUMENT_STATUSES)}
        for row in rows:
            status = row.get("status") or "uploaded"
            status_breakdown[status] = status_breakdown.get(status, 0) + 1

        total_chunks = _count_all_chunks(db)
        embedded_chunks = _count_all_embedded_chunks(db)

        return DocumentStatusSummary(
            total_documents=len(rows),
            processed_documents=status_breakdown.get("processed", 0),
            warning_documents=status_breakdown.get("processed_with_warnings", 0),
            failed_documents=status_breakdown.get("failed_extraction", 0),
            needs_ocr_documents=status_breakdown.get("needs_ocr", 0),
            embedding_pending_documents=status_breakdown.get("embedding_pending", 0),
            embedding_failed_documents=status_breakdown.get("embedding_failed", 0),
            total_chunks=total_chunks,
            embedded_chunks=embedded_chunks,
            pending_embeddings=max(total_chunks - embedded_chunks, 0),
            status_breakdown=status_breakdown,
        )
    except Exception as e:
        print(f"Error building document status summary: {e}")
        return DocumentStatusSummary()

def register_document(
    title: str,
    file_name: Optional[str] = None,
    total_pages: int = 0,
    source_type: str = "pdf",
    source_group: str = "general",
    domain: str = "finance",
    version: int = 1,
    file_hash: Optional[str] = None,
    status: str = "uploaded",
    metadata: Optional[Dict[str, Any]] = None,
    summary: Optional[str] = None,
    filename: Optional[str] = None,
    page_count: Optional[int] = None,
) -> str:
    """Register a new document in the database and return its ID."""
    if status not in ALLOWED_DOCUMENT_STATUSES:
        raise ValueError(f"Invalid status '{status}'.")

    normalized_file_name = file_name or filename
    if not normalized_file_name:
        raise ValueError("file_name is required.")

    normalized_total_pages = page_count if page_count is not None else total_pages
    db = get_db()

    response = db.table("documents").insert({
        "title": title,
        "file_name": normalized_file_name,
        "source_type": source_type,
        "source_group": source_group,
        "domain": domain,
        "version": version,
        "file_hash": file_hash,
        "status": status,
        "total_pages": normalized_total_pages,
        "total_chunks": 0,
        "uploaded_at": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
        "summary": summary,
    }).execute()

    return str(response.data[0]["id"])

def save_chunks(document_id: str, chunks: List[dict]):
    """
    Save chunks to document_chunks with Phase-1 fields.
    Updates document total_chunks.
    """
    if not chunks:
        return

    db = get_db()
    prepared_chunks = []
    for idx, chunk in enumerate(chunks):
        prepared_chunks.append({
            "document_id": chunk["document_id"],
            "chunk_index": chunk.get("chunk_index", idx),
            "page_start": chunk.get("page_start", chunk.get("page_number")),
            "page_end": chunk.get("page_end", chunk.get("page_number")),
            "section_title": chunk.get("section_title"),
            "chunk_text": chunk.get("chunk_text", chunk.get("content", "")),
            "token_count": chunk.get("token_count"),
            "chunk_type": chunk.get("chunk_type", "body"),
            "embedding": chunk.get("embedding"),
            "embedding_model": chunk.get("embedding_model"),
            "embedding_dimension": chunk.get("embedding_dimension"),
            "embedded_at": chunk.get("embedded_at"),
            "metadata": chunk.get("metadata", {}),
        })

    db.table("document_chunks").insert(prepared_chunks).execute()

    total_chunks = _count_total_chunks(db, document_id)
    db.table("documents").update({
        "total_chunks": total_chunks,
    }).eq("id", document_id).execute()

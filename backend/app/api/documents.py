"""
Documents API router - handles document listing, status, and upload ingestion.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.db import get_db
from app.models.document import (
    get_all_documents,
    get_document_by_id,
    get_document_status_summary,
    register_document,
    save_chunks,
)
from app.schemas.chat import (
    DocumentListResponse,
    DocumentStatusSummary,
    DocumentUploadResponse,
)
from app.services.embeddings import generate_embeddings
from app.services.ingestion import extract_pages, ingest_pdf_pipeline

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()


def _docs_dir() -> Path:
    docs_dir = Path(__file__).resolve().parents[2] / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir


def _sanitize_filename(filename: str) -> str:
    base_name = Path(filename or "document.pdf").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base_name).stem).strip("._") or "document"
    suffix = Path(base_name).suffix.lower() or ".pdf"
    return f"{stem}{suffix}"


def _unique_storage_path(filename: str) -> Path:
    docs_dir = _docs_dir()
    candidate = docs_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    counter = 1
    while True:
        alternate = docs_dir / f"{stem}_{timestamp}_{counter}{suffix}"
        if not alternate.exists():
            return alternate
        counter += 1


def _compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _determine_version(db, title: str, explicit_version: Optional[int]) -> int:
    if explicit_version is not None:
        return explicit_version

    latest_same_doc = (
        db.table("documents")
        .select("version")
        .eq("title", title)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return (latest_same_doc.data[0]["version"] + 1) if latest_same_doc.data else 1


def _quality_status(quality: Dict) -> str:
    score = float(quality.get("extraction_quality_score", 0.0) or 0.0)
    empty_ratio = float(quality.get("empty_page_ratio", 1.0) or 1.0)
    pages_with_text = int(quality.get("pages_with_text", 0) or 0)
    if pages_with_text == 0 or empty_ratio >= 0.70 or score < 0.25:
        return "needs_ocr"
    if score < 0.55 or empty_ratio >= 0.35:
        return "processed_with_warnings"
    return "embedding_pending"


def _refresh_document_counts(db, doc_id: str, total_pages: Optional[int] = None) -> Dict[str, int]:
    count_resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", doc_id)
        .execute()
    )
    embedded_resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", doc_id)
        .not_.is_("embedding", "null")
        .execute()
    )
    total_chunks = count_resp.count or 0
    embedded_chunks = embedded_resp.count or 0

    payload = {"total_chunks": total_chunks}
    if total_pages is not None:
        payload["total_pages"] = total_pages
    db.table("documents").update(payload).eq("id", doc_id).execute()

    return {
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
    }


def _upsert_document_metadata(db, doc_id: str, quality: Dict, extra_metadata: Dict, status: str) -> None:
    doc_resp = db.table("documents").select("metadata").eq("id", doc_id).limit(1).execute()
    existing_metadata = (doc_resp.data[0].get("metadata") if doc_resp.data else {}) or {}

    merged_metadata = {
        **existing_metadata,
        "extraction_quality": quality,
    }
    for key, value in extra_metadata.items():
        if value is None:
            merged_metadata.pop(key, None)
        else:
            merged_metadata[key] = value

    db.table("documents").update(
        {
            "metadata": merged_metadata,
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", doc_id).execute()


def _embed_document_chunks(db, doc_id: str) -> Dict[str, int | bool]:
    chunks = (
        db.table("document_chunks")
        .select("id, chunk_text")
        .eq("document_id", doc_id)
        .is_("embedding", "null")
        .order("chunk_index", desc=False)
        .execute()
        .data
        or []
    )

    if not chunks:
        counts = _refresh_document_counts(db, doc_id)
        return {"success": True, **counts}

    batch_size = 8
    updated = 0
    for index in range(0, len(chunks), batch_size):
        batch = chunks[index : index + batch_size]
        texts = [chunk["chunk_text"] for chunk in batch]
        vectors = generate_embeddings(texts)
        if not vectors or len(vectors) != len(batch):
            return {"success": False, "updated_chunks": updated}

        embedded_at = datetime.now(timezone.utc).isoformat()
        for chunk_row, vector in zip(batch, vectors):
            db.table("document_chunks").update(
                {
                    "embedding": vector,
                    "embedding_model": settings.embedding_model_id,
                    "embedding_dimension": len(vector),
                    "embedded_at": embedded_at,
                }
            ).eq("id", chunk_row["id"]).execute()
        updated += len(batch)

    counts = _refresh_document_counts(db, doc_id)
    return {"success": True, "updated_chunks": updated, **counts}


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """List all indexed documents directly from Supabase."""
    docs = get_all_documents()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/status", response_model=DocumentStatusSummary)
async def document_status():
    """Return aggregated knowledge-base pipeline status."""
    return get_document_status_summary()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    source_group: str = Form("general"),
    domain: str = Form("finance"),
    version: Optional[int] = Form(None),
):
    """
    Upload a PDF, ingest it, and embed its chunks synchronously.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    safe_name = _sanitize_filename(file.filename or "document.pdf")
    storage_path = _unique_storage_path(safe_name)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    storage_path.write_bytes(file_bytes)
    db = get_db()
    document_id: Optional[str] = None

    try:
        document_title = (title or Path(safe_name).stem.replace("_", " ").replace("-", " ")).strip()
        file_hash = _compute_file_hash(storage_path)

        duplicate = (
            db.table("documents")
            .select("id, file_name, version")
            .eq("file_hash", file_hash)
            .limit(1)
            .execute()
        )
        if duplicate.data:
            storage_path.unlink(missing_ok=True)
            existing = duplicate.data[0]
            raise HTTPException(
                status_code=409,
                detail=(
                    f"An identical PDF already exists as version {existing['version']} "
                    f"({existing['file_name']})."
                ),
            )

        total_pages = len(extract_pages(str(storage_path)))
        document_id = register_document(
            title=document_title,
            file_name=storage_path.name,
            total_pages=total_pages,
            source_type="pdf",
            source_group=source_group,
            domain=domain,
            version=_determine_version(db, document_title, version),
            file_hash=file_hash,
            status="processing",
            metadata={
                "ingestion_source": "api/documents/upload",
                "upload_file_name": file.filename,
            },
        )

        chunks, quality = ingest_pdf_pipeline(
            file_path=str(storage_path),
            document_id=document_id,
            source_group=source_group,
            source_metadata={
                "file_name": storage_path.name,
                "uploaded_via": "api",
            },
        )
        quality_status = _quality_status(quality)

        if quality_status == "needs_ocr":
            counts = _refresh_document_counts(db, document_id, total_pages=quality["total_pages"])
            _upsert_document_metadata(
                db,
                document_id,
                quality,
                {"warning": "extraction_quality_too_low"},
                "needs_ocr",
            )
            stored_doc = get_document_by_id(document_id)
            if not stored_doc:
                raise HTTPException(status_code=500, detail="Uploaded document was not saved correctly.")
            return DocumentUploadResponse(
                message="File uploaded, but extraction quality is too low. OCR is needed before normal retrieval.",
                document_id=document_id,
                title=stored_doc.title,
                file_name=stored_doc.file_name,
                source_group=stored_doc.source_group,
                domain=domain,
                status="needs_ocr",
                total_pages=stored_doc.total_pages,
                total_chunks=counts["total_chunks"],
                embedded_chunks=counts["embedded_chunks"],
                uploaded_at=stored_doc.uploaded_at,
                processed_at=datetime.now(timezone.utc),
                quality=quality,
            )

        if not chunks:
            counts = _refresh_document_counts(db, document_id, total_pages=quality["total_pages"])
            _upsert_document_metadata(
                db,
                document_id,
                quality,
                {"warning": "no_chunks_generated"},
                "failed_extraction",
            )
            raise HTTPException(
                status_code=422,
                detail="The PDF was uploaded, but no searchable chunks could be generated from it.",
            )

        save_chunks(document_id, chunks)
        counts = _refresh_document_counts(db, document_id, total_pages=quality["total_pages"])
        _upsert_document_metadata(
            db,
            document_id,
            quality,
            {"warning": "extraction_quality_low" if quality_status == "processed_with_warnings" else None},
            quality_status,
        )

        embed_result = _embed_document_chunks(db, document_id)
        final_status = "embedding_failed"
        if embed_result.get("success"):
            final_status = "processed_with_warnings" if quality_status == "processed_with_warnings" else "processed"

        db.table("documents").update(
            {
                "status": final_status,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", document_id).execute()

        stored_doc = get_document_by_id(document_id)
        if not stored_doc:
            raise HTTPException(status_code=500, detail="Uploaded document could not be reloaded from the registry.")

        message = "File uploaded, indexed, and embedded successfully."
        if final_status == "processed_with_warnings":
            message = "File uploaded and indexed with extraction warnings."
        elif final_status == "embedding_failed":
            message = "File uploaded and indexed, but embeddings failed. Retry embedding for this document."

        return DocumentUploadResponse(
            message=message,
            document_id=document_id,
            title=stored_doc.title,
            file_name=stored_doc.file_name,
            source_group=stored_doc.source_group,
            domain=domain,
            status=final_status,
            total_pages=stored_doc.total_pages,
            total_chunks=stored_doc.total_chunks,
            embedded_chunks=stored_doc.embedded_chunks,
            uploaded_at=stored_doc.uploaded_at,
            processed_at=stored_doc.processed_at,
            quality=quality,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if document_id:
            db.table("documents").update(
                {
                    "status": "failed_extraction",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail=f"Document upload failed: {exc}") from exc

"""
Local-friendly CLI script to generate and save embeddings for chunks missing vectors.

Recommended usage from backend folder:
  python scripts/run_embeddings.py --preflight
  python scripts/run_embeddings.py --missing-only
  python scripts/run_embeddings.py --document-id <uuid> --missing-only
  python scripts/run_embeddings.py --missing-only --batch-size 16

Scope:
- Select documents ready for embedding.
- Generate embeddings in configurable batches.
- Save vectors into document_chunks.
- Mark final document status.
- Does NOT extract PDFs or create chunks.
"""

import sys
import os
import argparse
import time
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import get_db
from app.core.config import get_settings
from app.services.embeddings import generate_embeddings


STATUS_EMBEDDING_PENDING = "embedding_pending"
STATUS_EMBEDDING_FAILED = "embedding_failed"
STATUS_PROCESSED = "processed"
STATUS_PROCESSED_WARNINGS = "processed_with_warnings"
STATUS_FAILED_EXTRACTION = "failed_extraction"
STATUS_NEEDS_OCR = "needs_ocr"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args():
    parser = argparse.ArgumentParser(description="Local embeddings CLI")
    parser.add_argument("--missing-only", action="store_true", help="Embed only rows with null embedding.")
    parser.add_argument("--document-id", dest="document_id", help="Embed only one document's chunks.")
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=8, help="Embedding batch size. Default: 8.")
    parser.add_argument("--limit-docs", dest="limit_docs", type=int, help="Process only first N candidate documents.")
    parser.add_argument("--max-retries", dest="max_retries", type=int, default=2, help="Retries per failed embedding batch. Default: 2.")
    parser.add_argument("--retry-sleep", dest="retry_sleep", type=float, default=2.0, help="Initial retry sleep in seconds. Default: 2.")
    parser.add_argument("--preflight", action="store_true", help="Validate embedding generation before processing documents.")
    parser.add_argument("--expected-dimension", dest="expected_dimension", type=int,
                        help="Optional expected vector dimension, e.g. 384 for all-MiniLM-L6-v2.")
    parser.add_argument("--dry-run", action="store_true", help="Show candidate work without generating/saving embeddings.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed error traceback")
    return parser.parse_args()


def _get_document_metadata(db, document_id: str) -> Dict[str, Any]:
    doc_resp = db.table("documents").select("metadata").eq("id", document_id).limit(1).execute()
    return (doc_resp.data[0].get("metadata") if doc_resp.data else {}) or {}


def _set_document_status(db, document_id: str, status: str, metadata_patch: Optional[Dict[str, Any]] = None):
    payload = {
        "status": status,
        "processed_at": now_iso(),
    }

    if metadata_patch:
        metadata = _get_document_metadata(db, document_id)
        metadata.update(metadata_patch)
        payload["metadata"] = metadata

    db.table("documents").update(payload).eq("id", document_id).execute()


def _candidate_document_ids(db, document_id: Optional[str] = None, limit_docs: Optional[int] = None) -> List[str]:
    if document_id:
        return [document_id]

    response = (
        db.table("documents")
        .select("id, status")
        .in_("status", [
            STATUS_EMBEDDING_PENDING,
            STATUS_EMBEDDING_FAILED,
            # Backward compatibility with previous script:
            STATUS_PROCESSED_WARNINGS,
        ])
        .execute()
    )

    doc_ids = [row["id"] for row in (response.data or [])]

    if limit_docs:
        doc_ids = doc_ids[:limit_docs]

    return doc_ids


def _count_chunks(db, document_id: str):
    total_resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .execute()
    )
    missing_resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .is_("embedding", "null")
        .execute()
    )
    return total_resp.count or 0, missing_resp.count or 0


def _update_document_status(db, document_id: str):
    total, missing = _count_chunks(db, document_id)
    metadata = _get_document_metadata(db, document_id)

    if total == 0:
        warning = metadata.get("warning")
        terminal_status = STATUS_NEEDS_OCR if warning == "extraction_quality_too_low" else STATUS_FAILED_EXTRACTION
        _set_document_status(db, document_id, terminal_status)
        return

    has_extraction_warning = metadata.get("warning") in {
        "extraction_quality_low",
        "extraction_quality_too_low",
    }

    if missing == 0:
        next_status = STATUS_PROCESSED_WARNINGS if has_extraction_warning else STATUS_PROCESSED
    else:
        next_status = STATUS_EMBEDDING_FAILED

    _set_document_status(db, document_id, next_status)


def _fetch_chunks(db, document_id: str, missing_only: bool) -> List[Dict[str, Any]]:
    query = (
        db.table("document_chunks")
        .select("id, chunk_text, chunk_index")
        .eq("document_id", document_id)
    )

    if missing_only:
        query = query.is_("embedding", "null")

    response = query.order("chunk_index", desc=False).execute()
    return response.data or []


def _validate_texts(texts: List[str]) -> List[str]:
    """
    Keep embedding input predictable for local/API providers.
    Empty strings commonly cause provider-specific failures.
    """
    cleaned = []
    for text in texts:
        if text is None:
            cleaned.append("")
        else:
            cleaned.append(str(text).strip())
    return cleaned


def _generate_embeddings_with_retry(
    texts: List[str],
    max_retries: int,
    retry_sleep: float,
    verbose: bool = False,
):
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            vectors = generate_embeddings(texts)
            return vectors
        except Exception as e:
            last_error = e
            if attempt >= max_retries:
                break

            sleep_for = retry_sleep * (2 ** attempt)
            print(f"  -> embedding attempt {attempt + 1} failed: {e}. Retrying in {sleep_for:.1f}s.")
            time.sleep(sleep_for)

    if verbose and last_error:
        traceback.print_exception(type(last_error), last_error, last_error.__traceback__)

    raise last_error


def _run_preflight(expected_dimension: Optional[int] = None) -> int:
    settings = get_settings()
    print("--- Embedding Preflight ---")
    print(f"Embedding model from settings: {getattr(settings, 'embedding_model_id', 'unknown')}")

    vectors = generate_embeddings(["embedding preflight test"])
    if not vectors or not vectors[0]:
        raise RuntimeError("Preflight failed: generate_embeddings returned no vector.")

    dimension = len(vectors[0])
    print(f"Generated test vector dimension: {dimension}")

    if expected_dimension and dimension != expected_dimension:
        raise RuntimeError(
            f"Preflight failed: expected dimension {expected_dimension}, got {dimension}."
        )

    print("Preflight passed.")
    return dimension


def _save_vectors_one_by_one(db, batch, vectors, settings):
    """
    Compatible with current Supabase client usage.
    If this becomes slow at scale, replace with a Postgres RPC bulk update.
    """
    embedded_at = now_iso()

    for chunk, vector in zip(batch, vectors):
        db.table("document_chunks").update(
            {
                "embedding": vector,
                "embedding_model": settings.embedding_model_id,
                "embedding_dimension": len(vector),
                "embedded_at": embedded_at,
            }
        ).eq("id", chunk["id"]).execute()


def main():
    print("--- Starting Local Embedding Generation ---")
    args = parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be greater than 0")

    if args.preflight:
        _run_preflight(args.expected_dimension)
        if not args.document_id and not args.missing_only:
            print("--- Preflight complete. No documents processed because only --preflight was requested. ---")
            return

    db = get_db()
    settings = get_settings()

    target_docs = _candidate_document_ids(
        db=db,
        document_id=args.document_id,
        limit_docs=args.limit_docs,
    )

    if not target_docs:
        print("No candidate documents for embedding.")
        return

    print(f"Selected {len(target_docs)} document(s) for embedding.")

    for doc_id in target_docs:
        try:
            # Safer default:
            # - all candidate runs embed missing only
            # - document-id embeds all only when user explicitly omits --missing-only
            missing_only = args.missing_only or not args.document_id

            chunks = _fetch_chunks(db, doc_id, missing_only=missing_only)

            if not chunks:
                _update_document_status(db, doc_id)
                print(f"Document {doc_id}: nothing to embed.")
                continue

            print(f"\nDocument {doc_id}: {len(chunks)} chunk(s) to embed.")

            if args.dry_run:
                total, missing = _count_chunks(db, doc_id)
                print(f"  -> dry run: total_chunks={total}, missing_embeddings={missing}")
                continue

            _set_document_status(
                db,
                doc_id,
                STATUS_EMBEDDING_PENDING,
                {
                    "embedding_state": "in_progress",
                    "embedding_started_at": now_iso(),
                    "embedding_last_batch_size": args.batch_size,
                },
            )

            updated_count = 0
            failed = False
            failure_reason = None

            for i in range(0, len(chunks), args.batch_size):
                batch_number = i // args.batch_size + 1
                batch = chunks[i:i + args.batch_size]
                texts = _validate_texts([c.get("chunk_text") for c in batch])

                if any(not text for text in texts):
                    failed = True
                    failure_reason = f"Batch {batch_number} contains empty chunk_text."
                    print(f"  -> {failure_reason}")
                    break

                print(f"  -> batch {batch_number} ({len(batch)} chunks)")

                try:
                    vectors = _generate_embeddings_with_retry(
                        texts=texts,
                        max_retries=args.max_retries,
                        retry_sleep=args.retry_sleep,
                        verbose=args.verbose,
                    )
                except Exception as e:
                    failed = True
                    failure_reason = f"Embedding generation failed at batch {batch_number}: {e}"
                    print(f"  -> {failure_reason}")
                    break

                if not vectors or len(vectors) != len(batch):
                    failed = True
                    failure_reason = (
                        f"Embedding output mismatch at batch {batch_number}: "
                        f"expected {len(batch)}, got {len(vectors) if vectors else 0}."
                    )
                    print(f"  -> {failure_reason}")
                    break

                if args.expected_dimension:
                    bad_dimensions = [
                        len(vector)
                        for vector in vectors
                        if len(vector) != args.expected_dimension
                    ]
                    if bad_dimensions:
                        failed = True
                        failure_reason = (
                            f"Dimension mismatch at batch {batch_number}: "
                            f"expected {args.expected_dimension}, got {bad_dimensions[0]}."
                        )
                        print(f"  -> {failure_reason}")
                        break

                try:
                    _save_vectors_one_by_one(db, batch, vectors, settings)
                except Exception as e:
                    failed = True
                    failure_reason = f"DB vector save failed at batch {batch_number}: {e}"
                    if args.verbose:
                        traceback.print_exc()
                    print(f"  -> {failure_reason}")
                    break

                updated_count += len(batch)
                print(f"  -> saved {updated_count}/{len(chunks)}")

            if failed:
                _set_document_status(
                    db,
                    doc_id,
                    STATUS_EMBEDDING_FAILED,
                    {
                        "embedding_state": "failed",
                        "embedding_error": failure_reason,
                        "embedding_failed_at": now_iso(),
                        "embedding_updated_count": updated_count,
                    },
                )
            else:
                _set_document_status(
                    db,
                    doc_id,
                    STATUS_EMBEDDING_PENDING,
                    {
                        "embedding_state": "completed",
                        "embedding_completed_at": now_iso(),
                        "embedding_updated_count": updated_count,
                    },
                )
                _update_document_status(db, doc_id)

        except Exception as e:
            print(f"Document {doc_id}: unexpected embedding failure: {e}")
            if args.verbose:
                traceback.print_exc()
            _set_document_status(
                db,
                doc_id,
                STATUS_EMBEDDING_FAILED,
                {
                    "embedding_error": str(e),
                    "embedding_failed_at": now_iso(),
                },
            )

    print("\n--- Embeddings Complete ---")


if __name__ == "__main__":
    main()

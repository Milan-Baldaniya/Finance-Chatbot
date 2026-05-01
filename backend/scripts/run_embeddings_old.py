"""
Script to generate and save embeddings for chunks missing vectors.
Examples:
  python scripts/run_embeddings.py --missing-only
  python scripts/run_embeddings.py --document-id <uuid>
"""

import sys
import os
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import get_db
from app.core.config import get_settings
from app.services.embeddings import generate_embeddings

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 3 embeddings CLI")
    parser.add_argument("--missing-only", action="store_true", help="Embed only rows with null embedding (default behavior).")
    parser.add_argument("--document-id", dest="document_id", help="Embed only one document's chunks.")
    return parser.parse_args()


def _candidate_document_ids(db, document_id: str = None):
    if document_id:
        return [document_id]

    response = (
        db.table("documents")
        .select("id, status")
        .in_("status", ["embedding_pending", "embedding_failed", "processed_with_warnings"])
        .execute()
    )
    return [row["id"] for row in (response.data or [])]


def _update_document_status(db, document_id: str):
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
    total = total_resp.count or 0
    missing = missing_resp.count or 0
    doc_resp = db.table("documents").select("metadata").eq("id", document_id).limit(1).execute()
    metadata = (doc_resp.data[0].get("metadata") if doc_resp.data else {}) or {}
    if total == 0:
        warning = metadata.get("warning")
        terminal_status = "needs_ocr" if warning == "extraction_quality_too_low" else "failed_extraction"
        db.table("documents").update(
            {
                "status": terminal_status,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", document_id).execute()
        return
    has_extraction_warning = bool(metadata.get("warning") == "extraction_quality_low")
    if missing == 0:
        next_status = "processed_with_warnings" if has_extraction_warning else "processed"
    else:
        next_status = "embedding_failed"
    db.table("documents").update(
        {
            "status": next_status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", document_id).execute()


def main():
    print("--- Starting Phase 3: Generating Embeddings ---")
    args = parse_args()
    db = get_db()
    settings = get_settings()

    target_docs = _candidate_document_ids(db, args.document_id)
    if not target_docs:
        print("✅ No candidate documents for embedding.")
        return

    batch_size = 8
    for doc_id in target_docs:
        query = db.table("document_chunks").select("id, chunk_text").eq("document_id", doc_id)
        if args.missing_only or not args.document_id:
            query = query.is_("embedding", "null")
        chunks = (query.order("chunk_index", desc=False).execute().data or [])

        if not chunks:
            _update_document_status(db, doc_id)
            print(f"Document {doc_id}: nothing to embed.")
            continue

        print(f"\nDocument {doc_id}: {len(chunks)} chunks to embed.")
        updated_count = 0
        failed = False

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c["chunk_text"] for c in batch]
            ids = [c["id"] for c in batch]
            print(f"  -> batch {i // batch_size + 1}")
            vectors = generate_embeddings(texts)
            if not vectors or len(vectors) != len(batch):
                print("  -> embedding failure for this batch; stopping document.")
                failed = True
                break

            embedded_at = datetime.now(timezone.utc).isoformat()
            for chunk_id, vector in zip(ids, vectors):
                db.table("document_chunks").update(
                    {
                        "embedding": vector,
                        "embedding_model": settings.embedding_model_id,
                        "embedding_dimension": len(vector),
                        "embedded_at": embedded_at,
                    }
                ).eq("id", chunk_id).execute()
            updated_count += len(batch)
            print(f"  -> saved {updated_count}/{len(chunks)}")

        if failed:
            db.table("documents").update(
                {
                    "status": "embedding_failed",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", doc_id).execute()
        else:
            _update_document_status(db, doc_id)

    print("\n--- Embeddings Complete ---")

if __name__ == "__main__":
    main()

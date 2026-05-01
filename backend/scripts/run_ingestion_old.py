"""
CLI script to trigger PDF ingestion manually.
Run from backend folder:
  python scripts/run_ingestion.py --file backend/docs/a.pdf
  python scripts/run_ingestion.py --folder backend/docs
  python scripts/run_ingestion.py --source-group policy_wordings
  python scripts/run_ingestion.py --document-id <uuid> --reprocess
"""

import sys
import os
import argparse
import hashlib
import csv
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Add the 'backend' dir to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.document import register_document, save_chunks
from app.services.ingestion import ingest_pdf_pipeline
from app.core.db import get_db


def compute_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_pdf_inventory(inventory_path: str) -> Dict:
    """
    Load PDF inventory CSV into a dict keyed by file_name.
    Expected columns:
      file_name, document_title, source_group, domain, priority, expected_use_case, version, notes
    """
    if not os.path.exists(inventory_path):
        return {}

    inventory = {}
    with open(inventory_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("file_name") or "").strip()
            if not key:
                continue
            inventory[key] = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    return inventory

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 2/3 ingestion CLI")
    parser.add_argument("--file", dest="file_path", help="Ingest one PDF file")
    parser.add_argument("--folder", dest="folder_path", help="Ingest all PDFs from a folder")
    parser.add_argument("--source-group", dest="source_group", help="Ingest PDFs from inventory source group")
    parser.add_argument("--document-id", dest="document_id", help="Reprocess one registered document")
    parser.add_argument("--reprocess", action="store_true", help="Allow reprocessing for --document-id")
    parser.add_argument("--max-files", dest="max_files", type=int, help="Process only first N selected PDFs")
    parser.add_argument("--skip-files", dest="skip_files", type=int, default=0, help="Skip first N selected PDFs")
    return parser.parse_args()


def resolve_docs_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))


def _default_title_from_file(filename: str) -> str:
    return os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")


def _resolve_inventory_path(docs_dir: str) -> str:
    return os.path.join(docs_dir, "pdf_inventory.csv")


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _select_files(args, docs_dir: str, inventory: Dict, db) -> List[str]:
    if args.document_id:
        doc_resp = (
            db.table("documents")
            .select("id, file_name")
            .eq("id", args.document_id)
            .limit(1)
            .execute()
        )
        if not doc_resp.data:
            print(f"Document not found: {args.document_id}")
            return []
        file_name = doc_resp.data[0]["file_name"]
        file_path = os.path.join(docs_dir, file_name)
        if not os.path.exists(file_path):
            print(f"Document file is missing on disk: {file_path}")
            return []
        return [file_path]

    if args.file_path:
        return [os.path.abspath(args.file_path)] if os.path.exists(args.file_path) else []

    if args.folder_path:
        folder = os.path.abspath(args.folder_path)
        if not os.path.isdir(folder):
            return []
        return sorted(
            [os.path.join(folder, name) for name in os.listdir(folder) if name.lower().endswith(".pdf")]
        )

    if args.source_group:
        selected = []
        for file_name, row in inventory.items():
            if (row.get("source_group") or "").strip().lower() == args.source_group.strip().lower():
                file_path = os.path.join(docs_dir, file_name)
                if os.path.exists(file_path):
                    selected.append(file_path)
        return sorted(selected)

    if not os.path.isdir(docs_dir):
        return []
    return sorted(
        [os.path.join(docs_dir, name) for name in os.listdir(docs_dir) if name.lower().endswith(".pdf")]
    )


def _determine_version(db, title: str, inventory_version: Optional[int]) -> int:
    if inventory_version is not None:
        return inventory_version
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
    score = quality["extraction_quality_score"]
    empty_ratio = quality["empty_page_ratio"]
    pages_with_text = quality["pages_with_text"]
    if pages_with_text == 0 or empty_ratio >= 0.70 or score < 0.25:
        return "needs_ocr"
    if score < 0.55 or empty_ratio >= 0.35:
        return "processed_with_warnings"
    return "embedding_pending"


def _upsert_document_metadata(db, doc_id: str, quality: Dict, extra_metadata: Dict, status: str):
    doc_resp = db.table("documents").select("metadata").eq("id", doc_id).limit(1).execute()
    existing_metadata = (doc_resp.data[0].get("metadata") if doc_resp.data else {}) or {}
    merged_metadata = {
        **existing_metadata,
        **extra_metadata,
        "extraction_quality": quality,
    }
    db.table("documents").update(
        {
            "metadata": merged_metadata,
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", doc_id).execute()


def _delete_document_chunks(db, doc_id: str):
    db.table("document_chunks").delete().eq("document_id", doc_id).execute()
    db.table("documents").update({"total_chunks": 0}).eq("id", doc_id).execute()


def _refresh_document_counts(db, doc_id: str, total_pages: Optional[int] = None):
    count_resp = (
        db.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", doc_id)
        .execute()
    )
    payload = {"total_chunks": count_resp.count or 0}
    if total_pages is not None:
        payload["total_pages"] = total_pages
    db.table("documents").update(payload).eq("id", doc_id).execute()


def _reprocess_existing_document(db, doc_id: str, file_path: str, inventory_row: Dict):
    file_name = os.path.basename(file_path)
    title = inventory_row.get("document_title") or _default_title_from_file(file_name)
    source_group = inventory_row.get("source_group") or "general"
    domain = inventory_row.get("domain") or "finance"
    file_hash = compute_file_hash(file_path)

    db.table("documents").update(
        {
            "title": title,
            "file_name": file_name,
            "source_type": "pdf",
            "source_group": source_group,
            "domain": domain,
            "file_hash": file_hash,
            "status": "processing",
            "total_pages": 0,
            "processed_at": None,
        }
    ).eq("id", doc_id).execute()
    _delete_document_chunks(db, doc_id)
    _refresh_document_counts(db, doc_id, total_pages=0)


def _register_new_document(db, file_path: str, inventory_row: Dict) -> Optional[Tuple[str, str, str, str, int]]:
    file_name = os.path.basename(file_path)
    title = inventory_row.get("document_title") or _default_title_from_file(file_name)
    source_group = inventory_row.get("source_group") or "general"
    domain = inventory_row.get("domain") or "finance"
    file_hash = compute_file_hash(file_path)

    exact_duplicate = (
        db.table("documents")
        .select("id, file_name, version")
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    if exact_duplicate.data:
        existing = exact_duplicate.data[0]
        print(
            f"Skipping '{title}': identical file already exists as version {existing['version']} ({existing['file_name']})."
        )
        return None

    inventory_version = _safe_int(inventory_row.get("version"))
    version = _determine_version(db, title, inventory_version)

    doc_id = register_document(
        title=title,
        file_name=file_name,
        total_pages=0,
        source_type="pdf",
        source_group=source_group,
        domain=domain,
        version=version,
        file_hash=file_hash,
        status="processing",
        metadata={
            "ingestion_source": "scripts/run_ingestion.py",
            "inventory": {
                "priority": inventory_row.get("priority"),
                "expected_use_case": inventory_row.get("expected_use_case"),
                "notes": inventory_row.get("notes"),
            },
        },
    )
    return doc_id, title, source_group, domain, version


def main():
    print("--- Starting Phase 2/3 Ingestion ---")
    args = parse_args()

    docs_dir = resolve_docs_dir()
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"Created '{docs_dir}' directory. Add PDFs and run again.")
        return

    db = get_db()
    inventory_path = _resolve_inventory_path(docs_dir)
    inventory = load_pdf_inventory(inventory_path)
    files = _select_files(args, docs_dir, inventory, db)
    if args.skip_files:
        files = files[args.skip_files :]
    if args.max_files:
        files = files[: args.max_files]
    if not files:
        print("No target PDFs found for requested command.")
        return

    for file_path in files:
        doc_id = None
        if not os.path.exists(file_path):
            print(f"Skipping missing file: {file_path}")
            continue

        file_name = os.path.basename(file_path)
        inv = inventory.get(file_name, {})
        title = inv.get("document_title") or _default_title_from_file(file_name)
        source_group = inv.get("source_group") or "general"

        try:
            if args.document_id:
                if not args.reprocess:
                    print(f"Skipping {file_name}: --document-id requires --reprocess for safety.")
                    continue
                doc_id = args.document_id
                _reprocess_existing_document(db, doc_id, file_path, inv)
                version_resp = db.table("documents").select("version").eq("id", doc_id).limit(1).execute()
                version = version_resp.data[0]["version"] if version_resp.data else 1
                print(f"\nReprocessing '{title}' (document_id={doc_id}, version={version})...")
            else:
                registered = _register_new_document(db, file_path, inv)
                if not registered:
                    continue
                doc_id, title, source_group, _, version = registered
                print(f"\nProcessing '{title}' (group={source_group}, version={version})...")

            chunks, quality = ingest_pdf_pipeline(
                file_path=file_path,
                document_id=doc_id,
                source_group=source_group,
                source_metadata={
                    "file_name": file_name,
                    "priority": inv.get("priority"),
                    "expected_use_case": inv.get("expected_use_case"),
                },
            )
            print(
                "  -> quality:"
                f" pages_with_text={quality['pages_with_text']},"
                f" avg_chars={quality['average_chars_per_page']},"
                f" empty_ratio={quality['empty_page_ratio']},"
                f" score={quality['extraction_quality_score']}"
            )
            print(f"  -> generated chunks: {len(chunks)}")

            status = _quality_status(quality)
            if status == "needs_ocr":
                _refresh_document_counts(db, doc_id, total_pages=quality["total_pages"])
                _upsert_document_metadata(
                    db,
                    doc_id,
                    quality,
                    {"warning": "extraction_quality_too_low"},
                    "needs_ocr",
                )
                print("  -> marked needs_ocr (no normal ingestion of low-quality extraction).")
                continue

            if len(chunks) == 0:
                _refresh_document_counts(db, doc_id, total_pages=quality["total_pages"])
                _upsert_document_metadata(
                    db,
                    doc_id,
                    quality,
                    {"warning": "no_chunks_generated"},
                    "failed_extraction",
                )
                print("  -> no chunks generated; marked failed_extraction.")
                continue

            save_chunks(doc_id, chunks)
            _refresh_document_counts(db, doc_id, total_pages=quality["total_pages"])
            _upsert_document_metadata(
                db,
                doc_id,
                quality,
                {"warning": "extraction_quality_low" if status == "processed_with_warnings" else None},
                status,
            )
            if status == "processed_with_warnings":
                print("  -> ingested with warnings; run embeddings next.")
            else:
                print("  -> marked embedding_pending.")

        except Exception as e:
            print(f"  -> ingestion failed for {file_name}: {e}")
            if doc_id:
                db.table("documents").update(
                    {
                        "status": "failed_extraction",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", doc_id).execute()

    print("\n--- Ingestion Complete ---")

if __name__ == "__main__":
    main()

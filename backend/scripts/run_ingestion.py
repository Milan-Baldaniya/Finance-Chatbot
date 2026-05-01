"""
Local-friendly CLI script to trigger PDF ingestion manually.

Recommended usage from backend folder:
  python scripts/run_ingestion.py --file backend/docs/a.pdf
  python scripts/run_ingestion.py --folder backend/docs --max-files 3
  python scripts/run_ingestion.py --source-group policy_wordings
  python scripts/run_ingestion.py --document-id <uuid> --reprocess
  python scripts/run_ingestion.py --file backend/docs/a.pdf --force

Scope:
- Register or reprocess PDF documents.
- Extract/chunk PDFs via app.services.ingestion.ingest_pdf_pipeline.
- Save chunks via app.models.document.save_chunks.
- Assign clear extraction/embedding-ready statuses.
- Does NOT generate embeddings.
"""

import sys
import os
import argparse
import hashlib
import csv
import json
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

# Add the 'backend' dir to the Python path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import register_document, save_chunks
from app.services.ingestion import ingest_pdf_pipeline
from app.core.db import get_db


STATUS_PROCESSING = "processing"
STATUS_EMBEDDING_PENDING = "embedding_pending"
STATUS_EMBEDDING_PENDING_WARNINGS = "embedding_pending_with_warnings"
STATUS_NEEDS_OCR = "needs_ocr"
STATUS_FAILED_EXTRACTION = "failed_extraction"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_pdf_inventory(inventory_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load PDF inventory CSV into a dict keyed by file_name.

    Expected columns:
      file_name, document_title, source_group, domain, priority,
      expected_use_case, version, notes
    """
    if not os.path.exists(inventory_path):
        return {}

    inventory: Dict[str, Dict[str, Any]] = {}
    with open(inventory_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("file_name") or "").strip()
            if not key:
                continue
            inventory[key] = {
                k: (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
            }
    return inventory


def parse_args():
    parser = argparse.ArgumentParser(description="Local PDF ingestion CLI")

    target = parser.add_mutually_exclusive_group()
    target.add_argument("--file", dest="file_path", help="Ingest one PDF file")
    target.add_argument("--folder", dest="folder_path", help="Ingest all PDFs from a folder")
    target.add_argument("--source-group", dest="source_group", help="Ingest PDFs from inventory source group")
    target.add_argument("--document-id", dest="document_id", help="Reprocess one registered document")

    parser.add_argument("--reprocess", action="store_true", help="Required safety flag for --document-id")
    parser.add_argument("--force", action="store_true", help="Reprocess existing identical file hash instead of skipping")
    parser.add_argument("--max-files", dest="max_files", type=int, help="Process only first N selected PDFs")
    parser.add_argument("--skip-files", dest="skip_files", type=int, default=0, help="Skip first N selected PDFs")
    parser.add_argument("--allow-low-quality-chunks", action="store_true",
                        help="Save generated chunks even when extraction quality would normally be marked needs_ocr")
    parser.add_argument("--dry-run", action="store_true", help="Show selected files without writing to DB")
    parser.add_argument("--verbose", action="store_true", help="Print detailed error traceback")

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


def _normalize_pdf_files(paths: List[str]) -> List[str]:
    return sorted([
        os.path.abspath(path)
        for path in paths
        if os.path.isfile(path) and path.lower().endswith(".pdf")
    ])


def _select_files(args, docs_dir: str, inventory: Dict[str, Dict[str, Any]], db) -> List[str]:
    if args.document_id:
        doc_resp = (
            db.table("documents")
            .select("id, file_name, metadata")
            .eq("id", args.document_id)
            .limit(1)
            .execute()
        )
        if not doc_resp.data:
            print(f"Document not found: {args.document_id}")
            return []

        row = doc_resp.data[0]
        metadata = row.get("metadata") or {}
        candidate_paths = []

        # Prefer explicit paths saved in metadata, but remain compatible with current DB.
        for key in ("original_file_path", "storage_path"):
            if metadata.get(key):
                candidate_paths.append(metadata[key])

        candidate_paths.append(os.path.join(docs_dir, row["file_name"]))

        for candidate in candidate_paths:
            candidate = os.path.abspath(candidate)
            if os.path.exists(candidate):
                return [candidate]

        print(f"Document file is missing on disk. Tried: {candidate_paths}")
        return []

    if args.file_path:
        file_path = os.path.abspath(args.file_path)
        return [file_path] if os.path.exists(file_path) else []

    if args.folder_path:
        folder = os.path.abspath(args.folder_path)
        if not os.path.isdir(folder):
            return []
        return _normalize_pdf_files([os.path.join(folder, name) for name in os.listdir(folder)])

    if args.source_group:
        selected = []
        for file_name, row in inventory.items():
            if (row.get("source_group") or "").strip().lower() == args.source_group.strip().lower():
                file_path = os.path.join(docs_dir, file_name)
                if os.path.exists(file_path):
                    selected.append(file_path)
        return _normalize_pdf_files(selected)

    if not os.path.isdir(docs_dir):
        return []

    return _normalize_pdf_files([os.path.join(docs_dir, name) for name in os.listdir(docs_dir)])


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


def _quality_status(quality: Dict[str, Any], allow_low_quality_chunks: bool, chunk_count: int) -> str:
    score = float(quality.get("extraction_quality_score") or 0)
    empty_ratio = float(quality.get("empty_page_ratio") or 0)
    pages_with_text = int(quality.get("pages_with_text") or 0)

    hard_ocr_condition = (
        pages_with_text == 0
        or empty_ratio >= 0.70
        or score < 0.25
    )

    warning_condition = (
        score < 0.55
        or empty_ratio >= 0.35
    )

    if hard_ocr_condition:
        if allow_low_quality_chunks and chunk_count > 0:
            return STATUS_EMBEDDING_PENDING_WARNINGS
        return STATUS_NEEDS_OCR

    if warning_condition:
        return STATUS_EMBEDDING_PENDING_WARNINGS

    return STATUS_EMBEDDING_PENDING


def _get_document_metadata(db, doc_id: str) -> Dict[str, Any]:
    doc_resp = db.table("documents").select("metadata").eq("id", doc_id).limit(1).execute()
    return (doc_resp.data[0].get("metadata") if doc_resp.data else {}) or {}


def _update_document_metadata_and_status(
    db,
    doc_id: str,
    quality: Dict[str, Any],
    extra_metadata: Dict[str, Any],
    status: str,
):
    existing_metadata = _get_document_metadata(db, doc_id)
    merged_metadata = {
        **existing_metadata,
        **{k: v for k, v in extra_metadata.items() if v is not None},
        "extraction_quality": quality,
        "last_ingestion_run_at": now_iso(),
    }

    db.table("documents").update(
        {
            "metadata": merged_metadata,
            "status": status,
            "processed_at": now_iso(),
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


def _prepare_existing_document_for_reprocess(
    db,
    doc_id: str,
    file_path: str,
    inventory_row: Dict[str, Any],
):
    file_name = os.path.basename(file_path)
    title = inventory_row.get("document_title") or _default_title_from_file(file_name)
    source_group = inventory_row.get("source_group") or "general"
    domain = inventory_row.get("domain") or "finance"
    file_hash = compute_file_hash(file_path)

    existing_metadata = _get_document_metadata(db, doc_id)
    metadata = {
        **existing_metadata,
        "original_file_path": os.path.abspath(file_path),
        "ingestion_source": "scripts/run_ingestion.py",
        "reprocessed_at": now_iso(),
    }

    db.table("documents").update(
        {
            "title": title,
            "file_name": file_name,
            "source_type": "pdf",
            "source_group": source_group,
            "domain": domain,
            "file_hash": file_hash,
            "status": STATUS_PROCESSING,
            "total_pages": 0,
            "processed_at": None,
            "metadata": metadata,
        }
    ).eq("id", doc_id).execute()

    _delete_document_chunks(db, doc_id)
    _refresh_document_counts(db, doc_id, total_pages=0)


def _find_existing_document_by_hash(db, file_hash: str) -> Optional[Dict[str, Any]]:
    resp = (
        db.table("documents")
        .select("id, file_name, version, title")
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def _register_or_prepare_document(
    db,
    file_path: str,
    inventory_row: Dict[str, Any],
    force: bool,
) -> Optional[Tuple[str, str, str, str, int, bool]]:
    """
    Returns:
      (doc_id, title, source_group, domain, version, is_reprocess)
    """
    file_name = os.path.basename(file_path)
    title = inventory_row.get("document_title") or _default_title_from_file(file_name)
    source_group = inventory_row.get("source_group") or "general"
    domain = inventory_row.get("domain") or "finance"
    file_hash = compute_file_hash(file_path)

    existing = _find_existing_document_by_hash(db, file_hash)

    if existing and not force:
        print(
            f"Skipping '{title}': identical file already exists as version "
            f"{existing['version']} ({existing['file_name']}). Use --force to reprocess."
        )
        return None

    if existing and force:
        doc_id = existing["id"]
        _prepare_existing_document_for_reprocess(db, doc_id, file_path, inventory_row)
        return doc_id, title, source_group, domain, existing.get("version") or 1, True

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
        status=STATUS_PROCESSING,
        metadata={
            "ingestion_source": "scripts/run_ingestion.py",
            "original_file_path": os.path.abspath(file_path),
            "inventory": {
                "priority": inventory_row.get("priority"),
                "expected_use_case": inventory_row.get("expected_use_case"),
                "notes": inventory_row.get("notes"),
            },
        },
    )

    return doc_id, title, source_group, domain, version, False


def _mark_failed_extraction(db, doc_id: str, error: Exception):
    metadata = _get_document_metadata(db, doc_id)
    metadata.update({
        "last_ingestion_error": str(error),
        "last_ingestion_failed_at": now_iso(),
    })

    db.table("documents").update(
        {
            "status": STATUS_FAILED_EXTRACTION,
            "processed_at": now_iso(),
            "metadata": metadata,
        }
    ).eq("id", doc_id).execute()


def main():
    print("--- Starting Local PDF Ingestion ---")
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
        files = files[args.skip_files:]

    if args.max_files:
        files = files[:args.max_files]

    if not files:
        print("No target PDFs found for requested command.")
        return

    print(f"Selected {len(files)} PDF(s).")

    if args.dry_run:
        for file_path in files:
            print(f"  - {file_path}")
        print("--- Dry run complete. No DB writes performed. ---")
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
                _prepare_existing_document_for_reprocess(db, doc_id, file_path, inv)

                version_resp = (
                    db.table("documents")
                    .select("version")
                    .eq("id", doc_id)
                    .limit(1)
                    .execute()
                )
                version = version_resp.data[0]["version"] if version_resp.data else 1
                print(f"\nReprocessing '{title}' (document_id={doc_id}, version={version})...")
            else:
                registered = _register_or_prepare_document(
                    db=db,
                    file_path=file_path,
                    inventory_row=inv,
                    force=args.force,
                )
                if not registered:
                    continue

                doc_id, title, source_group, _, version, is_reprocess = registered
                action = "Reprocessing" if is_reprocess else "Processing"
                print(f"\n{action} '{title}' (group={source_group}, version={version})...")

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

            total_pages = int(quality.get("total_pages") or 0)
            chunk_count = len(chunks)

            print(
                "  -> quality:"
                f" pages_with_text={quality.get('pages_with_text')},"
                f" avg_chars={quality.get('average_chars_per_page')},"
                f" empty_ratio={quality.get('empty_page_ratio')},"
                f" score={quality.get('extraction_quality_score')}"
            )
            print(f"  -> generated chunks: {chunk_count}")

            status = _quality_status(
                quality=quality,
                allow_low_quality_chunks=args.allow_low_quality_chunks,
                chunk_count=chunk_count,
            )

            if status == STATUS_NEEDS_OCR:
                _refresh_document_counts(db, doc_id, total_pages=total_pages)
                _update_document_metadata_and_status(
                    db=db,
                    doc_id=doc_id,
                    quality=quality,
                    extra_metadata={
                        "warning": "extraction_quality_too_low",
                        "recommended_next_step": "run_ocr_then_reprocess",
                    },
                    status=STATUS_NEEDS_OCR,
                )
                print("  -> marked needs_ocr. No chunks saved because extraction quality is too low.")
                continue

            if chunk_count == 0:
                _refresh_document_counts(db, doc_id, total_pages=total_pages)
                _update_document_metadata_and_status(
                    db=db,
                    doc_id=doc_id,
                    quality=quality,
                    extra_metadata={"warning": "no_chunks_generated"},
                    status=STATUS_FAILED_EXTRACTION,
                )
                print("  -> no chunks generated; marked failed_extraction.")
                continue

            save_chunks(doc_id, chunks)
            _refresh_document_counts(db, doc_id, total_pages=total_pages)

            warning = None
            if status == STATUS_EMBEDDING_PENDING_WARNINGS:
                warning = "extraction_quality_low"

            _update_document_metadata_and_status(
                db=db,
                doc_id=doc_id,
                quality=quality,
                extra_metadata={"warning": warning},
                status=status,
            )

            if status == STATUS_EMBEDDING_PENDING_WARNINGS:
                print("  -> chunks saved with extraction warnings. Run embeddings next.")
            else:
                print("  -> chunks saved. Marked embedding_pending.")

        except Exception as e:
            print(f"  -> ingestion failed for {file_name}: {e}")
            if args.verbose:
                traceback.print_exc()
            if doc_id:
                _mark_failed_extraction(db, doc_id, e)

    print("\n--- Ingestion Complete ---")


if __name__ == "__main__":
    main()

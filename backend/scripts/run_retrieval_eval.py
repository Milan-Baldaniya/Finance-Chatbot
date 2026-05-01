"""
Evaluate retrieval quality against a CSV dataset.

Usage examples:
  python scripts/run_retrieval_eval.py
  python scripts/run_retrieval_eval.py --dataset backend/docs/evaluation_dataset.csv
  python scripts/run_retrieval_eval.py --top-k 5
"""

import argparse
import csv
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.retrieval import confidence_for_chunks, retrieve_context


DEFAULT_DATASET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "docs", "evaluation_dataset.csv")
)


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate retrieval accuracy on a CSV dataset.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Path to evaluation CSV.")
    parser.add_argument("--top-k", type=int, default=5, help="Expected final chunk window for hit checks.")
    return parser.parse_args()


def load_dataset(dataset_path: str) -> List[Dict[str, str]]:
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    rows: List[Dict[str, str]] = []
    with open(dataset_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
            if not normalized.get("question"):
                continue
            rows.append(normalized)
    return rows


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _page_match(chunk: Dict, expected_page: Optional[str]) -> bool:
    if not expected_page:
        return False
    try:
        page = int(expected_page)
    except Exception:
        return False

    start = chunk.get("page_start")
    end = chunk.get("page_end", start)
    if start is None:
        return False
    try:
        start_int = int(start)
        end_int = int(end if end is not None else start)
    except Exception:
        return False
    return start_int <= page <= end_int


def evaluate_question(row: Dict[str, str], top_k: int) -> Dict:
    question = row["question"]
    retrieval = retrieve_context(question, history=[])
    final_chunks = retrieval.get("final_chunks", [])[:top_k]
    confidence = confidence_for_chunks(final_chunks)
    fallback = bool(retrieval.get("error")) or confidence == 0.0 or not final_chunks

    expected_title = _normalize(row.get("expected_document_title"))
    expected_group = _normalize(row.get("expected_source_group"))
    expected_page = row.get("expected_page_start")

    document_hit = any(_normalize(chunk.get("document_title")) == expected_title for chunk in final_chunks) if expected_title else False
    source_group_hit = any(_normalize(chunk.get("source_group")) == expected_group for chunk in final_chunks) if expected_group else False
    page_hit = any(_page_match(chunk, expected_page) for chunk in final_chunks) if expected_page else False

    first_chunk = final_chunks[0] if final_chunks else {}
    return {
        "question": question,
        "intent": retrieval.get("intent"),
        "rewritten_query": retrieval.get("rewritten_query"),
        "fallback": fallback,
        "error": retrieval.get("error"),
        "confidence": confidence,
        "document_hit": document_hit,
        "source_group_hit": source_group_hit,
        "page_hit": page_hit,
        "top_document": first_chunk.get("document_title"),
        "top_source_group": first_chunk.get("source_group"),
        "top_page_start": first_chunk.get("page_start"),
        "retrieved_chunks": len(final_chunks),
    }


def print_summary(results: List[Dict]):
    total = len(results)
    if total == 0:
        print("No evaluation rows found. Populate backend/docs/evaluation_dataset.csv and run again.")
        return

    fallback_count = sum(1 for result in results if result["fallback"])
    retrieval_errors = sum(1 for result in results if result["error"])
    document_hits = sum(1 for result in results if result["document_hit"])
    source_group_hits = sum(1 for result in results if result["source_group_hit"])
    page_hits = sum(1 for result in results if result["page_hit"])

    print("\n--- Retrieval Evaluation Summary ---")
    print(f"Total questions: {total}")
    print(f"Fallback responses: {fallback_count} ({fallback_count / total:.1%})")
    print(f"Retrieval errors: {retrieval_errors} ({retrieval_errors / total:.1%})")
    print(f"Expected document hit rate: {document_hits / total:.1%}")
    print(f"Expected source-group hit rate: {source_group_hits / total:.1%}")
    print(f"Expected page hit rate: {page_hits / total:.1%}")


def print_detailed_results(results: List[Dict]):
    print("\n--- Question Details ---")
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result['question']}")
        print(
            "   "
            f"intent={result['intent']} | confidence={result['confidence']:.3f} | "
            f"fallback={result['fallback']} | error={result['error']}"
        )
        print(
            "   "
            f"doc_hit={result['document_hit']} | group_hit={result['source_group_hit']} | "
            f"page_hit={result['page_hit']}"
        )
        print(
            "   "
            f"top_doc={result['top_document']} | top_group={result['top_source_group']} | "
            f"top_page={result['top_page_start']}"
        )


def main():
    args = parse_args()
    rows = load_dataset(args.dataset)
    results = [evaluate_question(row, args.top_k) for row in rows]
    print_summary(results)
    print_detailed_results(results)


if __name__ == "__main__":
    main()

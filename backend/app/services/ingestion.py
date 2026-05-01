"""
PDF Ingestion Service.
Handles page extraction, cleaning, quality scoring, section detection, and chunking.
"""

from pypdf import PdfReader
import re
from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Optional, Tuple


@dataclass
class ChunkProfile:
    chunk_size_chars: int
    overlap_chars: int


def resolve_chunk_profile(source_group: str) -> ChunkProfile:
    """
    Phase-2 defaults:
      - legal/policy: 900-1200 chars, overlap 180-250
      - brochure/faq: 1200-1500 chars, overlap 220-300
    """
    group = (source_group or "").lower()
    if group in {"policy_wordings", "compliance_docs", "legal_docs"}:
        return ChunkProfile(chunk_size_chars=1050, overlap_chars=220)
    if group in {"brochures", "faq_docs"}:
        return ChunkProfile(chunk_size_chars=1350, overlap_chars=260)
    if group in {"claim_docs"}:
        return ChunkProfile(chunk_size_chars=1150, overlap_chars=240)
    return ChunkProfile(chunk_size_chars=1200, overlap_chars=220)


def extract_pages(file_path: str) -> List[Dict]:
    """Extract raw text from every page."""
    reader = PdfReader(file_path)
    pages = []
    for page_num, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        pages.append({"page_number": page_num, "raw_text": raw_text})
    return pages


def _remove_repeated_edge_lines(lines_by_page: List[List[str]]) -> List[List[str]]:
    """
    Remove headers/footers repeated across many pages.
    """
    if len(lines_by_page) < 3:
        return lines_by_page

    header_counts: Dict[str, int] = {}
    footer_counts: Dict[str, int] = {}
    for lines in lines_by_page:
        if not lines:
            continue
        header = lines[0].strip().lower()
        footer = lines[-1].strip().lower()
        if header:
            header_counts[header] = header_counts.get(header, 0) + 1
        if footer:
            footer_counts[footer] = footer_counts.get(footer, 0) + 1

    threshold = max(2, int(len(lines_by_page) * 0.5))
    repeated_headers = {line for line, count in header_counts.items() if count >= threshold}
    repeated_footers = {line for line, count in footer_counts.items() if count >= threshold}

    cleaned = []
    for lines in lines_by_page:
        page_lines = list(lines)
        if page_lines and page_lines[0].strip().lower() in repeated_headers:
            page_lines = page_lines[1:]
        if page_lines and page_lines[-1].strip().lower() in repeated_footers:
            page_lines = page_lines[:-1]
        cleaned.append(page_lines)
    return cleaned


def clean_pages(raw_pages: List[Dict]) -> List[Dict]:
    """
    Apply cleaning rules:
      - null bytes
      - repeated whitespace
      - repeated headers/footers
      - page number strings
      - broken hyphenation
      - empty boilerplate lines
    """
    split_pages: List[List[str]] = []
    for page in raw_pages:
        text = (page.get("raw_text") or "").replace("\x00", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n")]
        split_pages.append(lines)

    split_pages = _remove_repeated_edge_lines(split_pages)

    cleaned_pages: List[Dict] = []
    for page, lines in zip(raw_pages, split_pages):
        filtered_lines: List[str] = []
        for line in lines:
            if not line:
                continue
            if re.fullmatch(r"(page\s*)?\d+(\s*/\s*\d+)?", line, flags=re.IGNORECASE):
                continue
            if line.lower() in {"confidential", "all rights reserved", "copyright"}:
                continue
            normalized = re.sub(r"[ \t]+", " ", line).strip()
            if normalized:
                filtered_lines.append(normalized)

        page_text = "\n".join(filtered_lines)
        page_text = re.sub(r"(\w)-\n(\w)", r"\1\2", page_text)   # de-hyphenate across line break
        page_text = re.sub(r"\n{3,}", "\n\n", page_text)
        cleaned_pages.append(
            {"page_number": page["page_number"], "raw_text": page.get("raw_text", ""), "cleaned_text": page_text.strip()}
        )
    return cleaned_pages


def calculate_extraction_quality(cleaned_pages: List[Dict]) -> Dict:
    page_count = len(cleaned_pages)
    chars_per_page = [len(page.get("cleaned_text", "")) for page in cleaned_pages]
    pages_with_text = sum(1 for c in chars_per_page if c > 0)
    average_chars_per_page = mean(chars_per_page) if chars_per_page else 0.0
    empty_page_ratio = (page_count - pages_with_text) / page_count if page_count else 1.0

    density_score = min(1.0, average_chars_per_page / 1400.0)
    coverage_score = 1.0 - empty_page_ratio
    extraction_quality_score = round((0.55 * coverage_score) + (0.45 * density_score), 4)

    return {
        "total_pages": page_count,
        "pages_with_text": pages_with_text,
        "average_chars_per_page": round(average_chars_per_page, 2),
        "empty_page_ratio": round(empty_page_ratio, 4),
        "extraction_quality_score": extraction_quality_score,
    }


def detect_sections(cleaned_pages: List[Dict]) -> List[Dict]:
    """
    Annotate pages with best-effort section titles from heading-like lines.
    """
    current_section = "General"
    annotated: List[Dict] = []

    for page in cleaned_pages:
        lines = [ln.strip() for ln in (page.get("cleaned_text") or "").split("\n") if ln.strip()]
        for line in lines[:8]:
            looks_heading = (
                len(line) <= 120
                and (line.isupper() or re.match(r"^\d+(\.\d+)*\s+[A-Za-z]", line) or line.endswith(":"))
            )
            if looks_heading:
                current_section = line.title() if line.isupper() else line
                break

        annotated.append(
            {
                "page_number": page["page_number"],
                "cleaned_text": page.get("cleaned_text", ""),
                "section_title": current_section,
            }
        )
    return annotated


def _choose_breakpoint(text: str, start: int, target_end: int) -> int:
    """
    Prefer chunk boundaries in order:
      headings/blank lines -> paragraph/bullet ends -> sentence ends -> whitespace.
    """
    end = min(target_end, len(text))
    if end >= len(text):
        return len(text)

    search_slice = text[start:end]
    if not search_slice.strip():
        return end

    candidates = []
    for pattern in [r"\n\n", r"\n[-*•]\s", r"[.!?]\s", r"\s"]:
        matches = list(re.finditer(pattern, search_slice))
        if matches:
            candidates = matches
            break

    if not candidates:
        return end

    last = candidates[-1]
    return start + max(1, last.end())


def build_chunks(
    document_id: str,
    section_pages: List[Dict],
    source_group: str,
    source_metadata: Optional[Dict] = None,
) -> List[Dict]:
    """
    Section-aware chunk generation over page text.
    """
    profile = resolve_chunk_profile(source_group)
    all_chunks: List[Dict] = []
    chunk_index = 0
    source_metadata = source_metadata or {}

    page_spans: List[Dict] = []
    full_text_parts: List[str] = []
    cursor = 0
    for page in section_pages:
        text = page.get("cleaned_text", "")
        if not text:
            continue
        part = (text + "\n\n")
        start = cursor
        end = cursor + len(part)
        page_spans.append(
            {
                "start": start,
                "end": end,
                "page_number": page["page_number"],
                "section_title": page.get("section_title", "General"),
            }
        )
        full_text_parts.append(part)
        cursor = end

    full_text = "".join(full_text_parts).strip()
    if not full_text:
        return all_chunks

    def range_pages(start_idx: int, end_idx: int) -> List[int]:
        pages = []
        for span in page_spans:
            if span["end"] <= start_idx or span["start"] >= end_idx:
                continue
            pages.append(span["page_number"])
        return pages

    def dominant_section(start_idx: int, end_idx: int) -> str:
        overlap_count: Dict[str, int] = {}
        for span in page_spans:
            overlap_start = max(start_idx, span["start"])
            overlap_end = min(end_idx, span["end"])
            if overlap_end <= overlap_start:
                continue
            section = span["section_title"]
            overlap_count[section] = overlap_count.get(section, 0) + (overlap_end - overlap_start)
        if not overlap_count:
            return "General"
        return sorted(overlap_count.items(), key=lambda kv: kv[1], reverse=True)[0][0]

    start = 0
    while start < len(full_text):
        target_end = start + profile.chunk_size_chars
        end = _choose_breakpoint(full_text, start, target_end)
        if end <= start:
            end = min(len(full_text), start + profile.chunk_size_chars)

        chunk_text = full_text[start:end].strip()
        if len(chunk_text) >= 80:
            pages = range_pages(start, end)
            page_start = pages[0] if pages else None
            page_end = pages[-1] if pages else page_start
            all_chunks.append(
                {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_title": dominant_section(start, end),
                    "chunk_text": chunk_text,
                    "token_count": len(chunk_text.split()),
                    "chunk_type": "section_body",
                    "metadata": {
                        "source_group": source_group,
                        **source_metadata,
                    },
                }
            )
            chunk_index += 1

        if end >= len(full_text):
            break
        # If a chunk is shorter than the configured overlap, naive overlap logic
        # can keep `start` unchanged and trap the pipeline in an infinite loop.
        next_start = max(0, end - profile.overlap_chars)
        start = next_start if next_start > start else end

    return all_chunks


def ingest_pdf_pipeline(
    file_path: str,
    document_id: str,
    source_group: str,
    source_metadata: Optional[Dict] = None,
) -> Tuple[List[Dict], Dict]:
    """
    End-to-end extraction/chunking pipeline for ingestion.
    Returns (chunks, quality_metrics).
    """
    raw_pages = extract_pages(file_path)
    cleaned_pages = clean_pages(raw_pages)
    quality = calculate_extraction_quality(cleaned_pages)
    section_pages = detect_sections(cleaned_pages)
    chunks = build_chunks(
        document_id=document_id,
        section_pages=section_pages,
        source_group=source_group,
        source_metadata=source_metadata,
    )
    return chunks, quality

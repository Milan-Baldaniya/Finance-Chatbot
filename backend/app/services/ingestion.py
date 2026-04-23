"""
PDF Ingestion Service.
Handles parsing PDFs, extracting text, and chunking.
"""

from pypdf import PdfReader
import re
from typing import List, Dict

# ── Chunking Strategy ──
# 500-800 words target, using characters (~3000 chars) as a proxy
CHUNK_SIZE_CHARS = 3000   # roughly 500-600 words
CHUNK_OVERLAP_CHARS = 600 # roughly 100-120 words

def clean_text(text: str) -> str:
    """Clean formatting artifacts, extra spaces from PDF text."""
    if not text:
        return ""
    # Replace multiple spaces with one
    text = re.sub(r'\s+', ' ', text)
    # Remove weird hidden characters if any
    text = text.replace('\x00', '')
    return text.strip()

def chunk_text(text: str, page_number: int, document_id: str) -> List[Dict]:
    """
    Split text into overlapping chunks.
    Returns a list of dictionaries ready to be inserted into Supabase.
    """
    chunks = []
    text_length = len(text)
    start = 0
    
    while start < text_length:
        end = start + CHUNK_SIZE_CHARS
        
        # If not at the end of the text, try to find a nice breaking point (like a newline or period)
        if end < text_length:
            # Look backwards for a period or newline within the last 150 chars
            split_point = text.rfind('.', start, end)
            if split_point == -1 or split_point < end - 150:
                split_point = text.rfind(' ', start, end)
                
            if split_point != -1 and split_point > start:
                end = split_point + 1 # Include the period/space

        chunk_content = text[start:end].strip()
        
        if len(chunk_content) > 50: # Only save meaningful chunks
            chunks.append({
                "document_id": document_id,
                "page_number": page_number,
                "content": chunk_content
                # 'embedding' is null for now. We will generate it in Phase 4.
            })
            
        start = end - CHUNK_OVERLAP_CHARS
        
    return chunks

def ingest_pdf(file_path: str, document_id: str) -> int:
    """
    Read a PDF, extract and clean text page-by-page, chunk it, and return the chunks.
    """
    reader = PdfReader(file_path)
    all_chunks = []
    
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        cleaned_text = clean_text(text)
        
        if cleaned_text:
            page_chunks = chunk_text(cleaned_text, page_num, document_id)
            all_chunks.extend(page_chunks)
            
    return all_chunks

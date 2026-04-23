"""
Database operations for Documents and Chunks via Supabase.
"""

from app.core.db import get_db
from app.schemas.chat import DocumentInfo
from typing import List

def get_all_documents() -> List[DocumentInfo]:
    """Retrieve a list of all indexed documents from Supabase."""
    try:
        db = get_db()
        # Fetch documents ordered by creation date descending
        response = db.table("documents").select(
            "id, title, filename, page_count, chunk_count, created_at"
        ).order("created_at", desc=True).execute()
        
        docs = []
        for row in response.data:
            docs.append(DocumentInfo(
                id=str(row["id"]),
                title=row["title"],
                filename=row["filename"],
                page_count=row.get("page_count", 0),
                chunk_count=row.get("chunk_count", 0),
                indexed_at=row["created_at"]
            ))
        return docs
    except Exception as e:
        print(f"Error fetching documents: {e}")
        return []

def register_document(title: str, filename: str, page_count: int = 0) -> str:
    """Register a new document in the database and return its ID."""
    db = get_db()
    response = db.table("documents").insert({
        "title": title,
        "filename": filename,
        "page_count": page_count,
        "chunk_count": 0
    }).execute()
    
    return str(response.data[0]["id"])

def save_chunks(document_id: str, chunks: List[dict]):
    """
    Save a list of chunk dictionaries to the document_chunks table.
    Update the chunk_count of the document.
    """
    if not chunks:
        return
        
    db = get_db()
    
    # Insert chunks
    db.table("document_chunks").insert(chunks).execute()
    
    # Update document chunk counter
    db.table("documents").update({
        "chunk_count": len(chunks)
    }).eq("id", document_id).execute()

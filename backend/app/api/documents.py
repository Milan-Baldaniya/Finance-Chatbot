"""
Documents API router — handles document listing and upload.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.schemas.chat import DocumentInfo, DocumentListResponse
from datetime import datetime

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """
    List all indexed documents directly from Supabase.
    """
    from app.models.document import get_all_documents
    docs = get_all_documents()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF document for future indexing.

    Phase 1 (scaffold): Accepts the file but does not process it yet.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    return {
        "message": f"File '{file.filename}' received. Indexing will be available in Phase 3.",
        "filename": file.filename,
    }

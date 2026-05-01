"""
Request and response schemas for the chat API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Chat Schemas ──

class ChatRequest(BaseModel):
    """Incoming chat question from the user."""
    question: str = Field(..., min_length=1, max_length=2000, description="The user's question")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")


class SourceCitation(BaseModel):
    """A single source reference returned alongside an answer."""
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    document_title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    chunk_preview: str = Field("", description="Short preview of the matched chunk")
    relevance_score: Optional[float] = None


class ChatResponse(BaseModel):
    """The API response to a chat question."""
    answer: str
    sources: list[SourceCitation] = []
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: Optional[float] = Field(None, description="Overall answer confidence 0-1")


# ── Document Schemas ──

class DocumentInfo(BaseModel):
    """Metadata about an indexed document in the registry."""
    id: str
    title: str
    file_name: str
    source_group: Optional[str] = None
    status: str
    total_pages: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    """Response listing all indexed documents."""
    documents: list[DocumentInfo] = []
    total: int = 0


class DocumentStatusSummary(BaseModel):
    """Aggregated knowledge-base pipeline status."""
    total_documents: int = 0
    processed_documents: int = 0
    warning_documents: int = 0
    failed_documents: int = 0
    needs_ocr_documents: int = 0
    embedding_pending_documents: int = 0
    embedding_failed_documents: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    pending_embeddings: int = 0
    status_breakdown: dict[str, int] = {}


class DocumentUploadResponse(BaseModel):
    """Response after synchronous PDF upload + indexing."""
    message: str
    document_id: str
    title: str
    file_name: str
    source_group: Optional[str] = None
    domain: Optional[str] = None
    status: str
    total_pages: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    quality: dict[str, float | int] = {}


# ── Health Schema ──

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str
    service: str

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
    document_title: str
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
    """Metadata about an indexed document."""
    id: str
    title: str
    filename: str
    page_count: int
    chunk_count: int
    indexed_at: datetime


class DocumentListResponse(BaseModel):
    """Response listing all indexed documents."""
    documents: list[DocumentInfo] = []
    total: int = 0


# ── Health Schema ──

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str
    service: str

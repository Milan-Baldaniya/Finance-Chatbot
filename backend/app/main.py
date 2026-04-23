"""
Finance Chatbot API — FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.schemas.chat import HealthResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="RAG-powered finance and insurance chatbot for India-related sources.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins so Vercel can connect seamlessly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(chat_router)
app.include_router(documents_router)


# ── Health Check ──
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Simple health endpoint to verify the API is running."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        service=settings.app_name,
    )


@app.get("/", tags=["health"])
async def root():
    """Root endpoint — redirect hint to docs."""
    return {
        "message": f"{settings.app_name} is running ✅",
        "docs": "/docs",
        "health": "/health",
    }

"""
Application configuration loaded from environment variables.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the Finance Chatbot API."""

    # ── App ──
    app_name: str = "Finance Chatbot API"
    app_version: str = "0.1.0"
    debug: bool = True

    # ── CORS ──
    frontend_url: str = "http://localhost:3000"

    # ── Supabase ──
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""

    # ── Hugging Face ──
    huggingface_api_token: str = ""

    # ── Models ──
    llm_model_id: str = "WiroAI/WiroAI-Finance-Qwen-7B"
    embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── RAG Retrieval ──
    rag_retrieval_candidates: int = 15
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.65
    enable_hybrid_search: bool = True
    enable_reranking: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Allow common environment values like 'release' and 'development'."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

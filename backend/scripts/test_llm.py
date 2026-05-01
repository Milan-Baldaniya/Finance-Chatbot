import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings
from app.services.llm import generate_grounded_answer


settings = get_settings()
token_preview = f"{settings.huggingface_api_token[:5]}..." if settings.huggingface_api_token else "missing"
print(f"Using Token: {token_preview}")

mock_chunks = [
    {
        "document_title": "Test Doc",
        "page_start": 1,
        "page_end": 1,
        "section_title": "Regulatory Overview",
        "chunk_text": (
            "In India, the Insurance Regulatory and Development Authority of India "
            "(IRDAI) is the primary regulatory body for the insurance sector."
        ),
    }
]

question = "What is the primary regulatory body for insurance in India?"
print(f"Testing question: {question}")

try:
    answer = generate_grounded_answer(question, mock_chunks, history=[], profile_summary="")
    print("\n--- LLM ANSWER ---")
    print(answer)
except Exception as exc:
    print("\n--- ERROR ---")
    print(exc)

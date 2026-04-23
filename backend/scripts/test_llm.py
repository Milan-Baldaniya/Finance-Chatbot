import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.llm import generate_answer
from app.core.config import get_settings

print(f"Using Token: {get_settings().huggingface_api_token[:5]}...")

# Mock retrieved chunks
mock_chunks = [
    {
        "document_title": "Test Doc",
        "page_number": 1,
        "content": "In India, the Insurance Regulatory and Development Authority of India (IRDAI) is the primary regulatory body for the insurance sector."
    }
]

question = "What is the primary regulatory body for insurance in India?"
print(f"Testing question: {question}")
try:
    answer = generate_answer(question, mock_chunks)
    print("\n--- LLM ANSWER ---")
    print(answer)
except Exception as e:
    print(f"\n--- ERROR ---")
    print(e)

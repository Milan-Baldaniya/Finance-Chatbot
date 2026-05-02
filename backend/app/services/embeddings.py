"""
Service for generating embeddings via Hugging Face Inference API.
"""

from huggingface_hub import InferenceClient
from app.core.config import get_settings
from typing import List

settings = get_settings()

def get_hf_client() -> InferenceClient:
    if not settings.huggingface_api_token:
        raise ValueError("HUGGINGFACE_API_TOKEN is missing in .env")
    return InferenceClient(token=settings.huggingface_api_token)

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using the configured HF model.
    """
    if not texts:
        return []
        
    client = get_hf_client()
    try:
        # feature_extraction returns a numpy-like list format.
        # the model 'sentence-transformers/all-MiniLM-L6-v2' returns vectors of 384 dimensions.
        response = client.feature_extraction(
            text=texts,
            model=settings.embedding_model_id
        )
        return response.tolist() if hasattr(response, 'tolist') else response
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        raise

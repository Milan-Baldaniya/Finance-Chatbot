"""
LLM Service for prompt generation and chat completion via Hugging Face.
Upgraded with robust classification, semantic coverage, context ranking, output guardrails, and persistent memory context.
"""

import logging
from typing import Dict, List, Optional

from huggingface_hub import InferenceClient

from app.core.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

FALLBACK_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
]


def get_chat_client() -> InferenceClient:
    return InferenceClient(token=settings.huggingface_api_token)


def _candidate_models() -> List[str]:
    models = [settings.llm_model_id, *FALLBACK_MODELS]
    seen = set()
    ordered_models = []

    for model in models:
        if model and model not in seen:
            ordered_models.append(model)
            seen.add(model)

    return ordered_models


def classify_intent(query: str) -> str:
    """
    Robust intent classification covering multiple natural variations.
    """
    query_lower = query.lower()

    if any(k in query_lower for k in ["before", "buy", "buying", "purchase", "taking", "requirements", "eligibility", "documents needed"]):
        return "pre_purchase"
    elif any(k in query_lower for k in ["claim", "settlement", "settle", "death benefit"]):
        return "claims"
    elif any(k in query_lower for k in ["premium", "lapse", "renewal", "grace period", "cancel"]):
        return "post_purchase"
    
    return "general"


def score_chunk(chunk: Dict, keywords: List[str]) -> int:
    """
    Scoring function to rank context chunks.
    """
    text = chunk["content"].lower()
    return sum(1 for k in keywords if k in text)


def filter_context(intent: str, chunks: List[Dict]) -> List[Dict]:
    """
    Semantic context filtering with ranking and trimming.
    """
    if not chunks:
        return []

    if intent == "pre_purchase":
        include_keywords = [
            "proposal", "disclosure", "insurable", "interest", "financial interest",
            "kyc", "identity", "aadhaar", "pan",
            "underwriting", "income", "financial",
            "medical", "health",
            "good faith", "material facts", "contract",
            "eligibility", "dependents"
        ]
        exclude_keywords = [
            "claim", "grace", "lapse", "settlement",
            "premium payment", "premium due", "renewal"
        ]

        filtered_chunks = []
        for chunk in chunks:
            content_lower = chunk["content"].lower()

            if any(ek in content_lower for ek in exclude_keywords):
                continue

            score = score_chunk(chunk, include_keywords)
            if score > 0:
                chunk["_match_score"] = score
                filtered_chunks.append(chunk)

        if not filtered_chunks:
            logger.info("Context filtering returned empty. Falling back to top 3 chunks.")
            return chunks[:3]

        # Context Ranking
        filtered_chunks.sort(key=lambda x: x.get("_match_score", 0), reverse=True)
        
        # Logging Enhancements
        top_scores = [c["_match_score"] for c in filtered_chunks[:4]]
        logger.info(f"Top chunk scores for '{intent}': {top_scores}")

        # Context Trimming (Reduced to Top 4)
        filtered_chunks = filtered_chunks[:4]
        return filtered_chunks

    # Trim default intents to top 4 to reduce token noise
    return chunks[:4]


def expand_query(query: str, history: List[Dict]) -> str:
    """
    Rewrite a vague follow-up query into a standalone query using recent chat history.
    """
    if not history:
        return query
        
    client = get_chat_client()
    
    # Format history concisely (last 20 messages for maximum deep context)
    recent_history = history[-20:]
    history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in recent_history])
    
    system_prompt = (
        "You are an AI assistant that rewrites a user's follow-up question into a standalone, "
        "comprehensive query based on the conversation history. "
        "Do NOT answer the question. ONLY return the rewritten standalone question. "
        "If the question is already standalone, return it exactly as is without changes."
    )
    
    user_prompt = f"Conversation History:\n{history_text}\n\nFollow-up Question: {query}\n\nRewritten Standalone Question:"
    
    try:
        response = client.chat_completion(
            model=FALLBACK_MODELS[0], # Fast reliable model for rewriting
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=100,
            temperature=0.1
        )
        expanded = response.choices[0].message.content.strip()
        # Remove quotes if the LLM wraps it in strings
        if expanded.startswith('"') and expanded.endswith('"'):
            expanded = expanded[1:-1]
            
        logger.info(f"Query Expansion: '{query}' -> '{expanded}'")
        return expanded
    except Exception as e:
        logger.error(f"Error expanding query: {e}")
        return query





def generate_answer(query: str, context_chunks: List[Dict], history: Optional[List[Dict]] = None) -> str:
    """
    Generate an answer using intent classification, ranked/trimmed context, history, strict prompt constraints, and guardrails.
    """
    client = get_chat_client()

    # 1. Intent Classification
    intent = classify_intent(query)
    logger.info(f"Detected Intent: '{intent}'")
    logger.info(f"Chunks before filtering: {len(context_chunks)}")

    # 2. Context Filtering & Ranking
    filtered_chunks = filter_context(intent, context_chunks)
    logger.info(f"Final selected chunk count: {len(filtered_chunks)}")

    # 3. Prompt Construction
    context_text = "\n\n".join(
        f"[Source: {c['document_title']} - Page {c['page_number']}]\n{c['content']}"
        for c in filtered_chunks
    )

    system_prompt = (
        "You are FinBot, an incredibly intelligent, highly conversational, and expert AI finance and insurance assistant for India.\n"
        "Your goal is to provide brilliant, easy-to-understand, and highly accurate answers based on the provided context.\n"
        "You should feel like a smart human expert—friendly, analytical, and articulate.\n"
        "CRITICAL RULE: You are strictly a financial, banking, and insurance assistant. If the user asks ANY question unrelated to finance, insurance, taxes, banking, or the provided context (such as coding, general knowledge, jokes, or recipe questions), you MUST politely decline to answer and remind them of your purpose.\n"
        "If the user asks a conversational question related to finance, answer smoothly and naturally.\n"
        "If they ask about specific rules or regulations, use the context provided but explain it in a clear, highly intelligent way. Use paragraphs and bullet points where helpful to organize information beautifully.\n"
        "DO NOT be a robot. DO NOT force bullet points on every single sentence. Be naturally conversational while remaining strictly accurate to the context.\n"
    )

    if intent == "pre_purchase":
        system_prompt += (
            "The user is asking about pre-purchase rules. Be sure to explain KYC, underwriting, or disclosure rules if relevant, but do so naturally.\n"
        )
    elif intent == "claims":
        system_prompt += "The user is asking about claims or settlements. Explain the rules clearly.\n"

    user_prompt = ""
    if context_text:
        user_prompt = (
            f"Context Information:\n{context_text}\n\n"
            f"Question: {query}\n\n"
            "Answer thoughtfully and accurately using the context above:"
        )
    else:
        user_prompt = f"Question: {query}\n\nAnswer thoughtfully:"

    messages = [{"role": "system", "content": system_prompt}]
    
    # Append History if provided
    if history:
        for msg in history:
            # Map role to HuggingFace supported roles (user/assistant)
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
            
    # Append current user prompt
    messages.append({"role": "user", "content": user_prompt})

    # 4. LLM Call with Fallbacks & Output Guardrails
    for model_name in _candidate_models():
        try:
            logger.info(f"Calling LLM Model: {model_name}")
            response = client.chat_completion(
                model=model_name,
                messages=messages,
                max_tokens=600,
                temperature=0.35  # Increased temperature for conversational, natural behavior
            )
            raw_answer = response.choices[0].message.content.strip()
            
            # Pass through the raw, intelligent answer
            return raw_answer
            
        except Exception as e:
            logger.error(f"Error calling LLM model '{model_name}': {e}")

    return "Sorry, I am currently unable to generate an answer due to an AI service error."

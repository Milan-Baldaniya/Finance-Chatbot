"""
LLM Service for prompt generation and chat completion via Hugging Face.
Upgraded with robust classification, semantic coverage, context ranking, output guardrails, and persistent memory context.
"""

import logging
import re
from typing import Dict, List, Optional

from huggingface_hub import InferenceClient

from app.core.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

FALLBACK_MODELS = [
    "WiroAI/WiroAI-Finance-Qwen-7B",
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
]
UNSUPPORTED_MODELS = set()

def _chunk_text(chunk: Dict) -> str:
    return chunk.get("chunk_text", chunk.get("content", "")) or ""

def _chunk_page(chunk: Dict) -> str:
    page_start = chunk.get("page_start", chunk.get("page_number"))
    page_end = chunk.get("page_end", page_start)
    if page_start and page_end and page_start != page_end:
        return f"{page_start}-{page_end}"
    if page_start:
        return str(page_start)
    return "N/A"


def _postprocess_grounded_answer(answer: str) -> str:
    """
    Keep the answer natural in the chat body.
    The UI already shows citations separately, so strip obvious
    source-reference lines if the model still emits them.
    """
    if not answer:
        return answer

    lines = []
    for line in answer.splitlines():
        if re.match(r"^\s*(document|page|section|source|sources|reference|references)\s*:", line, flags=re.IGNORECASE):
            continue
        lines.append(line)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned or answer.strip()


def get_chat_client() -> InferenceClient:
    return InferenceClient(token=settings.huggingface_api_token)


def _candidate_models() -> List[str]:
    models = [settings.llm_model_id, *FALLBACK_MODELS]
    seen = set()
    ordered_models = []

    for model in models:
        if model and model not in seen and model not in UNSUPPORTED_MODELS:
            ordered_models.append(model)
            seen.add(model)

    return ordered_models


def _remember_unsupported_model(model_name: str, error: Exception) -> None:
    message = str(error).lower()
    if "model_not_supported" in message or "not supported by any provider" in message:
        UNSUPPORTED_MODELS.add(model_name)


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
    text = _chunk_text(chunk).lower()
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
            content_lower = _chunk_text(chunk).lower()

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





def generate_answer(query: str, context_chunks: List[Dict], history: Optional[List[Dict]] = None, profile_summary: str = "") -> str:
    """
    Generate an answer using intent classification, ranked/trimmed context, history, user profile, and strict prompt constraints.
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
        f"[Source: {c.get('document_title', 'Unknown Document')} - Page {_chunk_page(c)}]\n{_chunk_text(c)}"
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

    # Inject user profile for personalized answers
    if profile_summary:
        system_prompt += (
            f"\n--- USER PROFILE ---\n{profile_summary}\n"
            "Use this profile as guidance to personalize your answers (e.g., age-appropriate plans, income-suitable products, smoker vs non-smoker premiums). "
            "But NEVER make final underwriting claims based on profile alone. If the profile is relevant to the question, mention how it applies. "
            "If the profile is irrelevant to the question, ignore it.\n"
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
                temperature=0.40
            )
            raw_answer = response.choices[0].message.content.strip()
            
            # Pass through the raw, intelligent answer
            return raw_answer
            
        except Exception as e:
            _remember_unsupported_model(model_name, e)
            logger.error(f"Error calling LLM model '{model_name}': {e}")

    return "Sorry, I am currently unable to generate an answer due to an AI service error."


def generate_grounded_answer(
    query: str,
    context_chunks: List[Dict],
    history: Optional[List[Dict]] = None,
    profile_summary: str = "",
) -> str:
    """
    Strict grounded answering using retrieved evidence.
    """
    client = get_chat_client()
    conversation_context = ""
    if history:
        recent_user_questions = [
            msg["content"].strip()
            for msg in history
            if msg.get("role") == "user" and msg.get("content")
        ][-4:]
        if recent_user_questions:
            conversation_context = "Conversation background (secondary, not evidence):\n" + "\n".join(
                f"- {question}" for question in recent_user_questions
            )

    context_text = "\n\n".join(
        (
            f"Document: {c.get('document_title', 'Unknown Document')}\n"
            f"Page: {_chunk_page(c)}\n"
            f"Section: {c.get('section_title', 'General')}\n"
            f"Text: {_chunk_text(c)}"
        )
        for c in context_chunks
    )

    system_prompt = (
        "You are FinBot, an incredibly intelligent, highly conversational, and expert AI finance and insurance assistant.\n"
        "Your goal is to provide brilliant, easy-to-understand, and highly accurate answers.\n"
        "Use the provided context as your primary source of truth. If the context contains the answer, base your response on it.\n"
        "If the context does not contain enough information, you may use your general expertise in finance, banking, and insurance to help the user, but politely clarify that you are drawing from general knowledge.\n"
        "Write like an intelligent chatbot: clear, direct, and natural. Feel like a smart human expert—friendly, analytical, and articulate.\n"
        "Do NOT mention document names, page numbers, citations, source labels, or phrases like "
        "'according to the provided context' in the answer body. The UI already shows sources separately.\n"
        "CRITICAL RULE: You are strictly a financial, banking, and insurance assistant. If the user asks ANY question unrelated to finance, insurance, taxes, banking, or the provided context (such as coding, general knowledge, jokes, or recipe questions), you MUST politely decline to answer and remind them of your purpose.\n"
        "Keep retrieved evidence as primary context. Chat history and profile are secondary.\n"
    )
    if profile_summary:
        system_prompt += f"\nProfile summary (secondary):\n{profile_summary}\n"

    user_prompt = (
        f"{conversation_context}\n\n" if conversation_context else ""
    ) + (
        f"Context:\n{context_text}\n\n"
        f"Question: {query}\n\n"
        "Answer naturally and directly. Do not include citations or source references in the answer body."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": user_prompt})

    for model_name in _candidate_models():
        try:
            response = client.chat_completion(
                model=model_name,
                messages=messages,
                max_tokens=500,
                temperature=0.40,
            )
            return _postprocess_grounded_answer(response.choices[0].message.content.strip())
        except Exception as e:
            _remember_unsupported_model(model_name, e)
            logger.error(f"Error calling LLM model '{model_name}' for grounded answer: {e}")

    return "Sorry, I am currently unable to generate an answer due to an AI service error."

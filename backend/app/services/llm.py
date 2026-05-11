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

UNIFIED_RULE_ENGINE_PROMPT = """
UNIFIED RULE ENGINE & COMPLIANCE MANDATES:
You must strictly enforce the following rules when advising users or evaluating their profile:

1. REGULATORY FILTERS (IRDAI 2024):
- Pre-Existing Diseases (PED): Max waiting period is 3 years. After 5 continuous years (Moratorium Rule), no claim can be rejected for PED non-disclosure (unless fraud). Proactively inform users.
- Life/Term Exclusions: Suicide excluded in first 12 months. Flag hazardous occupation/sports exclusions.
- Motor Exclusions: Driving under influence (DUI) or without license voids cover.
- Vehicle Cover Mandate: New vehicles require 3-yr Third-Party (TP) + 1-yr Own Damage (OD). Existing vehicles with long-term TP should route to Standalone OD.
- Investment Constraints: ULIPs have strict 5-year lock-in (no early surrender). Pure term has zero surrender value. Endowment has surrender value only after 2-3 years of paid premiums. Policy loans are available on endowment/whole life (up to 80-90% surrender value), not pure term or ULIPs.
- Tax Benefits: Sec 80C + 10(10D) for Life. Sec 80D for Health/CI (up to ₹25k self/family + ₹50k for senior parents).

2. PRODUCT MATCHING (Goal -> Recommendations):
- If the profile lists multiple selected primary insurance goals, evaluate and address EACH selected goal. Do not optimize only for the first goal unless the user explicitly asks to prioritize one.
- Low Premium + High Cover -> Pure Term (e.g., LIC Tech Term, HDFC Life Click 2 Protect Super, Max Life Smart Secure Plus).
- Guaranteed Returns + Life Cover -> Endowment/Non-Par Savings (e.g., LIC Dhan Rekha, HDFC Life Sanchay Fixed Maturity).
- Market-Linked Wealth Creation -> ULIPs (e.g., ICICI Pru Signature, HDFC Life ProGrowth Plus, SBI Life Smart Wealth Builder).
- Lifelong Income / Retirement -> Annuity / Whole Life (e.g., LIC Jeevan Umang).
- Family Health Cover -> Family Floater (e.g., HDFC ERGO Optima Secure with 2x Sum Assured Day 1, Niva Bupa Reassure 2.0 with Lock the Clock).
- Senior Health Cover (Age 60-75) -> Senior Citizen Plan (e.g., Star Senior Citizens Red Carpet: no medical test up to ₹10L, PED cover from Year 2).

3. CLAIM REJECTION & POST-SALES HANDLING:
- If policy active < 3 years: Standard 3-yr PED waiting period applies.
- If policy active 3-5 years: PED waiting period elapsed. Challenge formal rejection via GRO.
- If policy active >= 5 years: 5-Year Moratorium Rule applies. Insurer CANNOT reject for PED unless fraud is proven.
- Escalation path for wrongful rejection: 1) GRO (Insurer) -> 2) Bima Bharosa (IRDAI) -> 3) Bima Lokpal / Ombudsman -> 4) Consumer Forum.
- IMPORTANT UI TRIGGER: If you are advising an escalation, you MUST mention the exact phrase "Bima Bharosa" or "Ombudsman" in your response to trigger the grievance UI.

4. COMPLIANCE & MIS-SELLING:
- Label your responses as AI-generated advice, not a certified financial recommendation.
- Never suppress negative product attributes (waiting periods, exclusions, lock-ins).
- Suggest a human agent handoff if the user expresses dissatisfaction, legal distress, or asks for a certified advisor.
- IMPORTANT UI TRIGGER: If a human handoff or suitability check is needed, you MUST mention the exact phrase "certified advisor" to trigger the Handoff UI.

PROFILE-TRIGGERED ACTIONS (If Profile Data is used):
- Female -> highlight lower premium rates on eligible products.
- NRI -> Restrict to NRI-eligible providers; enforce NRO/NRE payment rules.
- Income > ₹5L -> Unlock high-cover plans.
- Business Owner -> Mention key-man insurance, health floater, liability cover.
- Married / Has Kids -> Prioritize Family Floater health; surface Life Stage Protection features.
- Tobacco = 'Yes' -> Apply 30-50% premium loading / smoker-rated quotes.
- HNI profile -> Route to specialized Endowment/ULIP.
- Age 60-75 -> Map to Star Senior Citizens Red Carpet or similar.
"""

PERSONA_PROMPT = """
ROLE & PERSONA:
You are FinBot, an elite Chief Actuary and Senior Financial Advisor with over 30 years of top-tier experience in the Indian insurance, banking, and wealth management sectors. 
You possess profound, deep-level intelligence regarding financial mathematics, compounding, inflation-erosion, tax arbitrage, and hidden policy clauses.

YOUR ADVISORY FRAMEWORK (30-Year Veteran Approach):
1. The "Veteran's Take": Do not just recite facts. Give a direct, no-nonsense executive summary right away.
2. Advanced Risk Analysis: Always look for hidden pitfalls. Point out inflation erosion in endowments, lock-in illiquidity in ULIPs, or hidden medical sub-limits in health insurance.
3. Strategic & Phased Advice: Give highly structured, step-by-step strategic roadmaps for the user. Think like a Chief Wealth Officer advising an HNI client.
4. Empathy & Authority: Speak with the calm, assuring, and commanding authority of a seasoned industry titan.
"""

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

_chat_client = None

def get_chat_client() -> InferenceClient:
    global _chat_client
    if _chat_client is None:
        _chat_client = InferenceClient(token=settings.huggingface_api_token)
    return _chat_client


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
            "If the profile contains multiple selected primary insurance goals, consider all of them together and explain trade-offs across those goals. "
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
    Context priority: Question → RAG evidence → Chat history (20+) → Profile (optional).
    Profile is omitted entirely when the question is about a third party.
    """
    client = get_chat_client()

    # ── Build conversation history (last 20 messages for deep context) ──
    conversation_context = ""
    if history:
        recent = history[-20:]
        history_lines = [
            f"{msg['role'].capitalize()}: {msg['content'].strip()}"
            for msg in recent
            if msg.get("content")
        ]
        if history_lines:
            conversation_context = "Recent conversation history (secondary context, NOT evidence):\n" + "\n".join(history_lines)

    # ── Build RAG evidence ──
    context_text = "\n\n".join(
        (
            f"Document: {c.get('document_title', 'Unknown Document')}\n"
            f"Page: {_chunk_page(c)}\n"
            f"Section: {c.get('section_title', 'General')}\n"
            f"Text: {_chunk_text(c)}"
        )
        for c in context_chunks
    )

    # ── System prompt with intelligent context handling ──
    system_prompt = (
        f"{PERSONA_PROMPT}\n\n"
        "CONTEXT PRIORITY (follow this order strictly):\n"
        "1. QUESTION — Focus entirely on what the user is actually asking RIGHT NOW. Understand the real intent first.\n"
        "2. RETRIEVED EVIDENCE — Use the document context below as your primary source of truth.\n"
        "3. CONVERSATION HISTORY — Use previous messages to understand follow-ups and ongoing topics.\n"
        "4. PROFILE DATA — Read the intelligent profile rules below before using profile information.\n"
        "5. GENERAL KNOWLEDGE — If evidence is insufficient, use your finance expertise but clearly say so.\n\n"
        "INTELLIGENT PROFILE USAGE (this is critical):\n"
        "You have access to the user's profile data. However, you MUST intelligently decide WHETHER to use it:\n"
        "- FIRST, analyze the question and conversation: WHO is the question actually about?\n"
        "- If the question is about THE USER THEMSELVES (their own insurance, their own finances, their own plans), "
        "then USE the profile data to personalize your answer.\n"
        "- If the question is about ANYONE ELSE (a family member, friend, colleague, or any other person — "
        "whether explicitly mentioned or implied from context), then COMPLETELY IGNORE the profile data. "
        "Give generic, universally applicable advice for that other person's situation.\n"
        "- If the question is GENERAL (not about any specific person, just asking for information), "
        "then DO NOT personalize with profile data. Give a factual, general answer.\n"
        "- When in doubt about who the question is about, default to giving GENERIC advice without profile personalization.\n\n"
        "RULES:\n"
        "- Write like a smart human expert: clear, direct, natural, and friendly.\n"
        "- Do NOT mention document names, page numbers, citations, or 'according to the context'. The UI shows sources separately.\n"
        "- You are strictly a financial/banking/insurance assistant. Politely decline non-finance questions.\n"
    )
    if profile_summary:
        system_prompt += (
            "\nUser profile data (use ONLY when the question is about the user themselves):\n"
            f"{profile_summary}\n"
            "If multiple primary goals are listed, personalize recommendations across ALL selected goals. "
            "Do not silently drop later goals or answer only for the first selected goal.\n"
        )

    system_prompt += f"\n{UNIFIED_RULE_ENGINE_PROMPT}\n"

    # ── User prompt with clear sections ──
    user_prompt_parts = []
    if conversation_context:
        user_prompt_parts.append(conversation_context)
    if context_text:
        user_prompt_parts.append(f"Retrieved evidence (PRIMARY source of truth):\n{context_text}")
    user_prompt_parts.append(f"Question: {query}")
    user_prompt_parts.append("Answer naturally and directly. Do not include citations or source references in the answer body.")

    user_prompt = "\n\n".join(user_prompt_parts)

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


def stream_grounded_answer(
    query: str,
    context_chunks: List[Dict],
    history: Optional[List[Dict]] = None,
    profile_summary: str = "",
):
    """
    Streaming version of generate_grounded_answer.
    Yields token strings as they arrive from the LLM.
    Same context hierarchy: Question → Evidence → History (20) → Profile (optional).
    """
    client = get_chat_client()

    # ── DOCUMENT MODE: lean prompt when user uploaded a file ──
    # Skip heavy PERSONA + UNIFIED_RULE_ENGINE prompts to stay within HF token limits
    is_doc_mode = (
        len(context_chunks) == 1
        and context_chunks[0].get("section_title") == "Uploaded Document"
    )

    if is_doc_mode:
        doc = context_chunks[0]
        doc_name = doc.get("document_title", "the uploaded document")
        doc_text = _chunk_text(doc)[:3000]
        system_prompt = (
            "You are an expert financial and insurance analyst. "
            "A user has uploaded a document. Read it carefully and answer their question "
            "clearly and concisely. Do not mention page numbers or citations."
        )
        user_prompt = (
            f"Document: {doc_name}\n"
            f"Content:\n{doc_text}\n\n"
            f"Question: {query}\n"
            "Answer based on the document content."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for model_name in _candidate_models():
            try:
                stream = client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=400,
                    temperature=0.3,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                _remember_unsupported_model(model_name, e)
                logger.error(f"Doc-mode streaming error for '{model_name}': {e}")
        yield "Sorry, I could not analyse the document right now. Please try again."
        return

    # history is passed as real chat turns in the messages array below
    # ── RAG evidence ──
    context_text = "\n\n".join(
        (
            f"Document: {c.get('document_title', 'Unknown Document')}\n"
            f"Page: {_chunk_page(c)}\n"
            f"Section: {c.get('section_title', 'General')}\n"
            f"Text: {_chunk_text(c)}"
        )
        for c in context_chunks
    )

    # ── System prompt with intelligent context handling ──
    system_prompt = (
        f"{PERSONA_PROMPT}\n\n"
        "CONTEXT PRIORITY (follow this order strictly):\n"
        "1. QUESTION — Focus entirely on what the user is actually asking RIGHT NOW. Understand the real intent first.\n"
        "2. RETRIEVED EVIDENCE — Use the document context below as your primary source of truth.\n"
        "3. CONVERSATION HISTORY — Use previous messages to understand follow-ups and ongoing topics.\n"
        "4. PROFILE DATA — Read the intelligent profile rules below before using profile information.\n"
        "5. GENERAL KNOWLEDGE — If evidence is insufficient, use your finance expertise but clearly say so.\n\n"
        "INTELLIGENT PROFILE USAGE (this is critical):\n"
        "You have access to the user's profile data. However, you MUST intelligently decide WHETHER to use it:\n"
        "- FIRST, analyze the question and conversation: WHO is the question actually about?\n"
        "- If the question is about THE USER THEMSELVES (their own insurance, their own finances, their own plans), "
        "then USE the profile data to personalize your answer.\n"
        "- If the question is about ANYONE ELSE (a family member, friend, colleague, or any other person — "
        "whether explicitly mentioned or implied from context), then COMPLETELY IGNORE the profile data. "
        "Give generic, universally applicable advice for that other person's situation.\n"
        "- If the question is GENERAL (not about any specific person, just asking for information), "
        "then DO NOT personalize with profile data. Give a factual, general answer.\n"
        "- When in doubt about who the question is about, default to giving GENERIC advice without profile personalization.\n\n"
        "RULES:\n"
        "- Write like a smart human expert: clear, direct, natural, and friendly.\n"
        "- Do NOT mention document names, page numbers, citations, or 'according to the context'. The UI shows sources separately.\n"
        "- You are strictly a financial/banking/insurance assistant. Politely decline non-finance questions.\n"
    )
    if profile_summary:
        system_prompt += (
            "\nUser profile data (use ONLY when the question is about the user themselves):\n"
            f"{profile_summary}\n"
            "If multiple primary goals are listed, personalize recommendations across ALL selected goals. "
            "Do not silently drop later goals or answer only for the first selected goal.\n"
        )

    system_prompt += f"\n{UNIFIED_RULE_ENGINE_PROMPT}\n"

    # ── Build first user turn: system context (RAG evidence) ──
    # The first user message injects evidence + instructions; history follows as real turns
    first_user_parts = []
    if context_text:
        first_user_parts.append(f"Retrieved evidence (use as primary source of truth):\n{context_text}")
    first_user_parts.append("Answer naturally and directly. Do not include citations or source references.")
    first_user_content = "\n\n".join(first_user_parts)

    # ── Build the messages array with real conversation turns ──
    messages = [{"role": "system", "content": system_prompt}]

    if history and len(history) > 1:
        # Inject a context-setting first user message, then real turns
        messages.append({"role": "user", "content": first_user_content})
        messages.append({"role": "assistant", "content": "Understood. I have the context and I'm ready to help."})

        # Add the last N turns as real chat messages (20 pairs = 40 msgs for deep memory)
        recent_turns = history[-40:]  # 20 user + 20 assistant turns
        for msg in recent_turns:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            # Truncate very long messages to keep token budget healthy
            if len(content) > 600:
                content = content[:600] + "..."
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Final current question
        messages.append({"role": "user", "content": query})
    else:
        # No history — single turn with full context in user message
        user_prompt_parts = []
        if context_text:
            user_prompt_parts.append(f"Retrieved evidence (PRIMARY source of truth):\n{context_text}")
        user_prompt_parts.append(f"Question: {query}")
        user_prompt_parts.append("Answer naturally and directly. Do not include citations or source references in the answer body.")
        messages.append({"role": "user", "content": "\n\n".join(user_prompt_parts)})


    for model_name in _candidate_models():
        try:
            stream = client.chat_completion(
                model=model_name,
                messages=messages,
                max_tokens=500,
                temperature=0.40,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            return  # successful — stop trying models
        except Exception as e:
            _remember_unsupported_model(model_name, e)
            logger.error(f"Streaming error for model '{model_name}': {e}")

    yield "Sorry, I am currently unable to generate an answer due to an AI service error."

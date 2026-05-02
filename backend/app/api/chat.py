from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.core.config import get_settings
from app.core.auth import get_current_user_id
from app.schemas.profile import UserProfilePayload
from app.services.llm import generate_grounded_answer
from app.services.retrieval import retrieve_context, confidence_for_chunks
from app.services.memory import create_session, delete_session, get_all_sessions, get_recent_messages, get_session_history, save_message, session_belongs_to_user
from app.services.profile import get_profile as fetch_profile
from app.services.profile import get_profile_summary, upsert_profile

router = APIRouter()
settings = get_settings()

def _chunk_text(chunk: dict) -> str:
    return chunk.get("chunk_text", chunk.get("content", "")) or ""

def _chunk_page_number(chunk: dict):
    return chunk.get("page_start", chunk.get("page_number"))


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """
    Accept a user question, find relevant chunks (with memory support), 
    and return an AI answer with source citations.
    Requires authentication.
    """
    # 1. Manage Session and Memory
    session_id = request.session_id
    
    # If no session_id provided, create a new chat session
    if not session_id:
        title = request.question[:35] + ("..." if len(request.question) > 35 else "")
        session_id = create_session(user_id, title)
        if not session_id:
            raise HTTPException(status_code=500, detail="Failed to create chat session.")
    elif not session_belongs_to_user(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    
    save_message(session_id, user_id, "user", request.question)
    history = get_recent_messages(session_id, user_id, limit=50)
    
    # Fetch user profile for personalized answers
    profile_summary = get_profile_summary(user_id)
    
    try:
        retrieval = retrieve_context(request.question, history)
        top_chunks = retrieval["final_chunks"]
        confidence = confidence_for_chunks(top_chunks)

        if retrieval["error"] or confidence < settings.rag_similarity_threshold:
            top_chunks = []
            confidence = 0.0

        answer = generate_grounded_answer(
            query=request.question,
            context_chunks=top_chunks,
            history=history,
            profile_summary=profile_summary,
        )
        assistant_message = save_message(session_id, user_id, "assistant", answer)
        
        # 6. Map citations
        sources = []
        for chunk in top_chunks:
            preview = _chunk_text(chunk)[:100].replace('\n', ' ') + "..."
            sources.append(
                SourceCitation(
                    chunk_id=chunk.get("chunk_id"),
                    document_id=chunk.get("document_id"),
                    document_title=chunk.get('document_title', 'Unknown Document'),
                    page_start=chunk.get("page_start"),
                    page_end=chunk.get("page_end"),
                    section_title=chunk.get("section_title"),
                    page_number=_chunk_page_number(chunk),
                    chunk_preview=preview,
                    relevance_score=chunk.get('blended_score', chunk.get('similarity', 0.0))
                )
            )
            
        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
            created_at=assistant_message["created_at"] if assistant_message else datetime.utcnow(),
            confidence=confidence
        )
        
    except Exception as e:
        print(f"Chat API Error: {e}")
        fallback_answer = "Sorry, I am currently unable to process your request."
        fallback_message = save_message(session_id, user_id, "assistant", fallback_answer)

        return ChatResponse(
            answer=fallback_answer,
            sources=[],
            session_id=session_id,
            created_at=fallback_message["created_at"] if fallback_message else datetime.utcnow(),
            confidence=0.0
        )


@router.get("/api/retrieval/debug")
async def retrieval_debug(
    query: str,
    session_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Internal retrieval debug endpoint.
    """
    history = []
    if session_id:
        if not session_belongs_to_user(session_id, user_id):
            raise HTTPException(status_code=404, detail="Session not found")
        history = get_recent_messages(session_id, user_id, limit=50)

    retrieval = retrieve_context(query=query, history=history)
    return {
        "query": query,
        "session_id": session_id,
        "rewritten_query": retrieval.get("rewritten_query"),
        "intent": retrieval.get("intent"),
        "filters": retrieval.get("filters"),
        "vector_hits": retrieval.get("vector_hits", []),
        "keyword_hits": retrieval.get("keyword_hits", []),
        "final_chunks": retrieval.get("final_chunks", []),
        "error": retrieval.get("error"),
    }


@router.get("/api/sessions")
async def get_sessions_endpoint(user_id: str = Depends(get_current_user_id)):
    """Returns only the current authenticated user's sessions."""
    return get_all_sessions(user_id)


@router.get("/api/chat/{session_id}")
async def get_chat_history_endpoint(session_id: str, user_id: str = Depends(get_current_user_id)):
    """Returns history only if the session belongs to the current user."""
    if not session_belongs_to_user(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_session_history(session_id, user_id)
    return messages


@router.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, user_id: str = Depends(get_current_user_id)):
    """Deletes a user-owned session and its messages."""
    if not session_belongs_to_user(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if not delete_session(session_id, user_id):
        raise HTTPException(status_code=500, detail="Failed to delete session")

    return {"success": True, "session_id": session_id}


@router.get("/api/profile")
async def get_profile_endpoint(user_id: str = Depends(get_current_user_id)):
    """Fetch current user profile and onboarding status."""
    try:
        profile = fetch_profile(user_id)
        if not profile:
            return {"onboarding_completed": False}

        return profile
    except Exception:
        return {"onboarding_completed": False}


@router.post("/api/profile/onboarding")
async def complete_onboarding(
    payload: UserProfilePayload,
    user_id: str = Depends(get_current_user_id),
):
    """Create or update the authenticated user's onboarding profile."""
    try:
        return upsert_profile(user_id, payload)
    except Exception as e:
        print(f"Profile onboarding error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save profile.")


@router.put("/api/profile")
async def update_profile(
    payload: UserProfilePayload,
    user_id: str = Depends(get_current_user_id),
):
    """Update the authenticated user's profile."""
    try:
        return upsert_profile(user_id, payload)
    except Exception as e:
        print(f"Profile update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile.")


@router.get("/api/auth/me")
async def auth_me(user_id: str = Depends(get_current_user_id)):
    """Lightweight bootstrap endpoint — confirms the user is authenticated and returns onboarding status."""
    try:
        profile = fetch_profile(user_id)
        onboarding_done = profile.get("onboarding_completed", False) if profile else False
        
        return {
            "user_id": user_id,
            "onboarding_completed": onboarding_done
        }
    except Exception:
        return {
            "user_id": user_id,
            "onboarding_completed": False
        }

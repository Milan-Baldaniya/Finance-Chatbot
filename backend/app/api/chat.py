from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.core.db import get_db
from app.core.auth import get_current_user_id
from app.schemas.profile import UserProfilePayload
from app.services.llm import generate_answer, expand_query
from app.services.embeddings import generate_embeddings
from app.services.memory import create_session, delete_session, get_all_sessions, get_recent_messages, get_session_history, save_message, session_belongs_to_user
from app.services.profile import get_profile as fetch_profile
from app.services.profile import get_profile_summary, upsert_profile

router = APIRouter()


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
        # 2. Expand/Rewrite Query for better retrieval if it's a follow-up
        standalone_query = expand_query(request.question, history)
        
        # 3. Embed the standalone query
        query_vectors = generate_embeddings([standalone_query])
        if not query_vectors:
            raise HTTPException(status_code=500, detail="Failed to embed query.")
        query_embedding = query_vectors[0]
        
        # 4. RETRIEVAL (PDFs Only)
        db = get_db()
        pdf_response = db.rpc(
            "match_document_chunks", 
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.2, 
                "match_count": 5
            }
        ).execute()
        
        top_chunks = pdf_response.data if pdf_response.data else []
        
        # 5. Generate Answer via LLM (passing original query, history, and profile)
        answer = generate_answer(request.question, top_chunks, history, profile_summary)
        assistant_message = save_message(session_id, user_id, "assistant", answer)
        
        # 6. Map citations
        sources = []
        for chunk in top_chunks:
            preview = chunk.get('content', '')[:100].replace('\n', ' ') + "..."
            sources.append(
                SourceCitation(
                    document_title=chunk.get('document_title', 'Unknown Document'),
                    page_number=chunk.get('page_number'),
                    chunk_preview=preview,
                    relevance_score=chunk.get('similarity', 0.0)
                )
            )
            
        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
            created_at=assistant_message["created_at"] if assistant_message else datetime.utcnow(),
            confidence=max((s.relevance_score for s in sources), default=0.0)
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

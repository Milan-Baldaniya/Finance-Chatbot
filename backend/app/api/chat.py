import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.core.config import get_settings
from app.core.auth import get_current_user_id
from app.schemas.profile import UserProfilePayload
from app.services.llm import generate_grounded_answer, stream_grounded_answer
from app.services.retrieval import retrieve_context, confidence_for_chunks
from app.services.memory import create_session, delete_session, get_all_sessions, get_recent_messages, get_session_history, save_message, session_belongs_to_user
from app.services.profile import get_profile as fetch_profile
from app.services.profile import build_profile_suggestions, get_profile_primary_goals, get_profile_summary, upsert_profile

router = APIRouter()
settings = get_settings()

def _chunk_text(chunk: dict) -> str:
    return chunk.get("chunk_text", chunk.get("content", "")) or ""

THIRD_PARTY_TERMS = {
    "father", "mother", "parent", "parents", "wife", "husband", "spouse",
    "son", "daughter", "child", "children", "friend", "colleague", "employee",
    "brother", "sister", "uncle", "aunt", "grandfather", "grandmother",
}

PERSONAL_ADVICE_TERMS = {
    "i", "me", "my", "mine", "myself", "we", "our", "us", "suggest",
    "suggestion", "suggestions", "recommend", "recommendation",
    "recommendations", "advice", "best", "buy", "choose", "plan", "policy",
    "cover", "coverage", "premium", "need", "suitable", "should", "goal",
    "goals",
}


def _should_use_profile_goals_for_retrieval(query: str, history: list[dict]) -> bool:
    text = " ".join(
        [query, *[(msg.get("content") or "") for msg in (history or [])[-4:]]]
    ).lower()
    words = {word.strip(".,?!:;()[]{}\"'") for word in text.split()}

    if THIRD_PARTY_TERMS.intersection(words):
        return False

    return bool(PERSONAL_ADVICE_TERMS.intersection(words))


def _query_with_profile_goals(query: str, primary_goals: list[str], history: list[dict]) -> str:
    if not primary_goals or not _should_use_profile_goals_for_retrieval(query, history):
        return query
    goal_context = "; ".join(primary_goals)
    return (
        f"{query}\n\n"
        f"User selected primary insurance goals for personalization: {goal_context}. "
        "Retrieve context relevant to every selected goal, not only the first one."
    )

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
import io

def _chunk_page_number(chunk: dict):
    return chunk.get("page_start", chunk.get("page_number"))

@router.post("/api/chat/parse-document")
async def parse_document(file: UploadFile = File(...)):
    """Extract text from an uploaded document for ad-hoc chat context."""
    filename = (file.filename or "").lower()
    content = ""
    try:
        file_bytes = await file.read()
        
        if filename.endswith(".pdf"):
            import pypdf
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    content += text + "\n"
        elif filename.endswith(".docx"):
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            content = "\n".join([para.text for para in doc.paragraphs])
        elif filename.endswith(".txt"):
            content = file_bytes.decode('utf-8', errors='ignore')
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload PDF, DOCX, or TXT.")
        
        # Limit extracted text size to avoid massive context window explosions
        max_chars = 40000 # Roughly 10k tokens
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[Document truncated due to length constraints]"

        return {"filename": file.filename, "content": content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {str(e)}")

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
    
    # Always pass profile — the LLM intelligently decides whether to use it
    profile_summary = get_profile_summary(user_id)
    primary_goals = get_profile_primary_goals(user_id)
    
    try:
        retrieval_query = _query_with_profile_goals(request.question, primary_goals, history)
        retrieval = retrieve_context(retrieval_query, history)
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


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """
    SSE streaming chat endpoint.
    Sends token events as they arrive, then a final metadata event with sources.
    """
    session_id = request.session_id

    # ── STEP 1: Parse document context FIRST (before any DB writes) ──
    # Format from frontend: "[Attached Document: {name}]\n{doc_text}\n\n{user_question}"
    raw_question = request.question
    adhoc_chunk = None

    if raw_question.startswith("[Attached Document:"):
        try:
            first_newline = raw_question.index("\n")
            header = raw_question[:first_newline]
            doc_name = header[len("[Attached Document: "):-1].strip()
            rest = raw_question[first_newline + 1:]

            if "\n\n" in rest:
                doc_body, user_query = rest.split("\n\n", 1)
                user_query = user_query.strip()
            else:
                doc_body = rest
                user_query = ""

            doc_body = doc_body.strip()
            if not user_query:
                user_query = f"Please summarize and explain this document: {doc_name}"

            print(f"[DOC UPLOAD] name={doc_name!r}, body_len={len(doc_body)}, query={user_query!r}")

            adhoc_chunk = {
                "chunk_text": doc_body[:3000],   # ~750 tokens — well within HF free API limits
                "document_title": doc_name,
                "section_title": "Uploaded Document",
                "page_start": None,
                "page_end": None,
                "chunk_id": None,
                "document_id": None,
                "blended_score": 1.0,
            }
            raw_question = user_query  # Only the clean user question from here on

        except Exception as parse_err:
            print(f"[DOC UPLOAD] Parse error: {parse_err}. Using full question as fallback.")
            raw_question = request.question

    # ── STEP 2: Create/validate session using CLEAN question as title ──
    if not session_id:
        title = raw_question[:35] + ("..." if len(raw_question) > 35 else "")
        session_id = create_session(user_id, title)
        if not session_id:
            raise HTTPException(status_code=500, detail="Failed to create chat session.")
    elif not session_belongs_to_user(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found.")

    # ── STEP 3: Save ONLY the clean question to DB (never the raw 40k doc body) ──
    save_message(session_id, user_id, "user", raw_question)
    history = get_recent_messages(session_id, user_id, limit=40)

    # Always pass profile — the LLM intelligently decides whether to use it
    profile_summary = get_profile_summary(user_id)
    primary_goals = get_profile_primary_goals(user_id)

    # When a document is uploaded, skip RAG retrieval entirely — the doc IS the context
    if adhoc_chunk:
        top_chunks = [adhoc_chunk]
        confidence = 1.0
    else:
        # Run retrieval synchronously before streaming
        try:
            retrieval_query = _query_with_profile_goals(raw_question, primary_goals, history)
            retrieval = retrieve_context(retrieval_query, history)
            top_chunks = retrieval["final_chunks"]
            confidence = confidence_for_chunks(top_chunks)

            if retrieval["error"] or confidence < settings.rag_similarity_threshold:
                top_chunks = []
                confidence = 0.0
        except Exception as e:
            print(f"Retrieval error in stream: {e}")
            top_chunks = []
            confidence = 0.0

    def event_generator():
        full_answer = []
        try:
            for token in stream_grounded_answer(
                query=raw_question,
                context_chunks=top_chunks,
                history=history,
                profile_summary=profile_summary,
            ):
                full_answer.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Save the complete answer
            complete_text = "".join(full_answer)
            assistant_message = save_message(session_id, user_id, "assistant", complete_text)

            # Build citations
            sources = []
            for chunk in top_chunks:
                preview = _chunk_text(chunk)[:100].replace('\n', ' ') + "..."
                sources.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "document_title": chunk.get("document_title", "Unknown Document"),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "section_title": chunk.get("section_title"),
                    "page_number": _chunk_page_number(chunk),
                    "chunk_preview": preview,
                    "relevance_score": chunk.get("blended_score", chunk.get("similarity", 0.0)),
                })

            meta = {
                "type": "done",
                "session_id": session_id,
                "confidence": confidence,
                "sources": sources,
                "created_at": (
                    assistant_message["created_at"]
                    if assistant_message
                    else datetime.utcnow().isoformat()
                ),
            }
            yield f"data: {json.dumps(meta)}\n\n"
        except Exception as e:
            print(f"Stream error: {e}")
            error_msg = "Sorry, I am currently unable to process your request."
            yield f"data: {json.dumps({'type': 'token', 'content': error_msg})}\n\n"
            save_message(session_id, user_id, "assistant", error_msg)
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'confidence': 0.0, 'sources': [], 'created_at': datetime.utcnow().isoformat()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@router.get("/api/profile/suggestions")
async def get_profile_suggestions_endpoint(user_id: str = Depends(get_current_user_id)):
    """Return fast profile-aware starter questions for a new chat."""
    return {"suggestions": build_profile_suggestions(fetch_profile(user_id))}


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

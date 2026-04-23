import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.core.db import get_db
from app.services.llm import generate_answer, expand_query
from app.services.embeddings import generate_embeddings
from app.services.memory import save_message, get_recent_messages

router = APIRouter()

@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Accept a user question, find relevant chunks (with memory support), 
    and return an AI answer with source citations.
    """
    # 1. Manage Session and Memory
    session_id = request.session_id or str(uuid.uuid4())
    save_message(session_id, "user", request.question)
    # Fetch the last 50 messages to ensure massive conversational context memory
    history = get_recent_messages(session_id, limit=50)
    
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
        
        # Search PDF chunks
        pdf_response = db.rpc(
            "match_document_chunks", 
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.2, 
                "match_count": 5
            }
        ).execute()
        
        top_chunks = pdf_response.data if pdf_response.data else []
        
        # 5. Generate Answer via LLM (passing original query and history)
        answer = generate_answer(request.question, top_chunks, history)
        save_message(session_id, "assistant", answer)
        
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
            created_at=datetime.utcnow(),
            confidence=max((s.relevance_score for s in sources), default=0.0)
        )
        
    except Exception as e:
        print(f"Chat API Error: {e}")
        fallback_answer = "Sorry, I am currently unable to process your request."
        save_message(session_id, "assistant", fallback_answer)
        
        return ChatResponse(
            answer=fallback_answer,
            sources=[],
            session_id=session_id,
            created_at=datetime.utcnow(),
            confidence=0.0
        )

@router.get("/api/sessions")
async def get_sessions():
    from app.services.memory import get_all_sessions
    return get_all_sessions()

@router.get("/api/chat/{session_id}")
async def get_chat_history(session_id: str):
    from app.services.memory import get_session_history
    messages = get_session_history(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")
    return messages

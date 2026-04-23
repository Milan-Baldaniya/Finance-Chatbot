"""
Chat Memory Service.
Handles persisting and retrieving conversation history from Supabase.
"""
from typing import List, Dict
import logging
from app.core.db import get_db

logger = logging.getLogger(__name__)

def save_message(session_id: str, role: str, content: str):
    """
    Save a single message to the chat_messages table.
    """
    db = get_db()
    try:
        db.table("chat_messages").insert({
            "session_id": session_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        logger.error(f"Error saving message to memory: {e}")

def get_recent_messages(session_id: str, limit: int = 6) -> List[Dict]:
    """
    Fetch the most recent messages for a given session.
    """
    db = get_db()
    try:
        response = db.table("chat_messages")\
            .select("role, content, created_at")\
            .eq("session_id", session_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        messages = response.data
        if not messages:
            return []
        
        messages.reverse()
        return messages
    except Exception as e:
        logger.error(f"Error fetching memory: {e}")
        return []

def get_all_sessions() -> List[Dict]:
    """
    Fetch a list of distinct session_ids with the first user message to use as a title.
    """
    db = get_db()
    try:
        response = db.table("chat_messages")\
            .select("session_id, content, created_at")\
            .eq("role", "user")\
            .order("created_at", desc=False)\
            .execute()
        
        sessions_map = {}
        for msg in response.data:
            sid = msg["session_id"]
            if sid not in sessions_map:
                title = msg["content"]
                sessions_map[sid] = {
                    "session_id": sid,
                    "title": title[:35] + "..." if len(title) > 35 else title,
                    "created_at": msg["created_at"]
                }
        
        sessions_list = list(sessions_map.values())
        sessions_list.sort(key=lambda x: x["created_at"], reverse=True)
        return sessions_list
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return []

def get_session_history(session_id: str) -> List[Dict]:
    """
    Fetch the complete chat history for a single session to load it into the UI.
    """
    db = get_db()
    try:
        response = db.table("chat_messages")\
            .select("id, role, content, created_at")\
            .eq("session_id", session_id)\
            .order("created_at", desc=False)\
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching session history: {e}")
        return []

"""
Chat Memory Service.
Handles persisting and retrieving conversation history from Supabase.
"""
from typing import List, Dict
import logging
from app.core.db import get_db

logger = logging.getLogger(__name__)

def create_session(user_id: str, title: str) -> str:
    db = get_db()
    try:
        res = db.table("chat_sessions").insert({
            "user_id": user_id,
            "title": title
        }).execute()
        return res.data[0]["id"]
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return ""

def session_belongs_to_user(session_id: str, user_id: str) -> bool:
    db = get_db()
    try:
        response = db.table("chat_sessions")\
            .select("id")\
            .eq("id", session_id)\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        return bool(response.data)
    except Exception as e:
        logger.error(f"Error checking session ownership: {e}")
        return False

def save_message(session_id: str, user_id: str, role: str, content: str):
    db = get_db()
    try:
        db.table("chat_messages").insert({
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        logger.error(f"Error saving message to memory: {e}")

def get_recent_messages(session_id: str, user_id: str, limit: int = 50) -> List[Dict]:
    db = get_db()
    try:
        response = db.table("chat_messages")\
            .select("role, content, created_at")\
            .eq("session_id", session_id)\
            .eq("user_id", user_id)\
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

def get_all_sessions(user_id: str) -> List[Dict]:
    db = get_db()
    try:
        response = db.table("chat_sessions")\
            .select("id, title, created_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=False)\
            .execute()
        
        sessions_list = []
        for row in response.data:
            sessions_list.append({
                "session_id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"]
            })
            
        sessions_list.sort(key=lambda x: x["created_at"], reverse=True)
        return sessions_list
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return []

def get_session_history(session_id: str, user_id: str) -> List[Dict]:
    db = get_db()
    try:
        response = db.table("chat_messages")\
            .select("id, role, content, created_at")\
            .eq("session_id", session_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=False)\
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching session history: {e}")
        return []

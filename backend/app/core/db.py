"""
Database client initialization.
"""

from supabase import create_client, Client
from app.core.config import get_settings

settings = get_settings()

def get_db() -> Client:
    """Return an authenticated Supabase client using the service role key."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase URL and Service Role Key must be set in .env")
        
    return create_client(
        settings.supabase_url, 
        settings.supabase_service_role_key
    )

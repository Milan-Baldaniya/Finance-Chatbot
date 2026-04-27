from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings

settings = get_settings()
security = HTTPBearer()

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Validates the Supabase JWT and returns the user_id.
    """
    token = credentials.credentials
    try:
        # Supabase signs JWTs using the project JWT secret.
        # But we don't have the JWT secret in our .env, only the anon key.
        # Wait, the frontend will pass the token. We can decode it.
        # Supabase JWTs don't require the secret if we just want to decode the payload.
        # However, for security, we MUST verify the signature. 
        # Since we might not have the JWT secret locally set up yet, 
        # for this MVP we will use the Supabase client to verify the user.
        from app.core.db import get_db
        supabase = get_db()
        
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
        return user_response.user.id
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

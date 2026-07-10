# app/api/auth.py
from fastapi import Depends, Header, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.jwt_helper import verify_jwt
from app.core.settings import settings

security = HTTPBearer(auto_error=False)

async def get_authenticated_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    auth: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> str:
    """
    Extracts verified user_id.
    Supports either a trusted gateway-injected X-User-ID header OR a direct JWT Bearer token.
    """
    # 1. Trusted Gateway Header
    if x_user_id:
        return x_user_id
        
    # 2. Direct JWT Bearer Token validation
    if auth and auth.credentials:
        jwt_secret = settings.mcp.jwt_secret.get_secret_value() if settings.mcp.jwt_secret else None
        if not jwt_secret:
            raise HTTPException(status_code=500, detail="JWT secret not configured on server")
            
        payload = verify_jwt(auth.credentials, jwt_secret)
        if not payload or "sub" not in payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return payload["sub"]
        
    raise HTTPException(status_code=401, detail="Missing authentication (X-User-ID header or Bearer token)")

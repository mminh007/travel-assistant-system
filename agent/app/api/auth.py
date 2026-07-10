from fastapi import Header, HTTPException

def get_authenticated_user_id(x_user_id: str = Header(None, alias="X-User-Id")) -> str:
    """
    Extracts the authenticated user ID from the request headers.
    In a microservice architecture, the API Gateway usually handles JWT verification
    and forwards the authenticated user's ID via the X-User-Id header.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing X-User-Id header")
    return x_user_id

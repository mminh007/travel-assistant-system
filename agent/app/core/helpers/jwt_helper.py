# app/core/jwt_helper.py
import jwt

def _get_secret_value(secret: any) -> str:
    if hasattr(secret, 'get_secret_value'):
        return secret.get_secret_value()
    return str(secret)

def sign_jwt(payload: dict, secret: str) -> str:
    actual_secret = _get_secret_value(secret)
    return jwt.encode(payload, actual_secret, algorithm="HS256")

def verify_jwt(token: str, secret: str) -> dict | None:
    actual_secret = _get_secret_value(secret)
    try:
        return jwt.decode(token, actual_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


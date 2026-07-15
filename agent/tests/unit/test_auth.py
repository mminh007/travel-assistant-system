import pytest
import time
import jwt
from app.core.helpers.jwt_helper import sign_jwt, verify_jwt

def test_valid_token_round_trip():
    payload = {"sub": "user123", "exp": time.time() + 300}
    secret = "my_super_secret"
    token = sign_jwt(payload, secret)
    
    verified_payload = verify_jwt(token, secret)
    assert verified_payload is not None
    assert verified_payload["sub"] == "user123"

def test_expired_token():
    payload = {"sub": "user123", "exp": time.time() - 300}
    secret = "my_super_secret"
    token = sign_jwt(payload, secret)
    
    verified_payload = verify_jwt(token, secret)
    assert verified_payload is None

def test_tampered_token():
    payload = {"sub": "user123", "exp": time.time() + 300}
    secret = "my_super_secret"
    token = sign_jwt(payload, secret)
    
    # Tamper with the token payload
    parts = token.split(".")
    parts[1] = parts[1] + "a"
    tampered_token = ".".join(parts)
    
    verified_payload = verify_jwt(tampered_token, secret)
    assert verified_payload is None

def test_wrong_secret():
    payload = {"sub": "user123", "exp": time.time() + 300}
    token = sign_jwt(payload, "secret1")
    
    verified_payload = verify_jwt(token, "secret2")
    assert verified_payload is None

def test_missing_sub_claim():
    # Our verify_jwt does not enforce 'sub' internally (interceptor does), but let's check it passes payload correctly
    payload = {"exp": time.time() + 300}
    secret = "secret"
    token = sign_jwt(payload, secret)
    
    verified_payload = verify_jwt(token, secret)
    assert verified_payload is not None
    assert "sub" not in verified_payload

def test_alg_none_attempt():
    payload = {"sub": "user123", "exp": time.time() + 300}
    # Create an unencrypted token with alg=none
    token = jwt.encode(payload, "", algorithm="none")
    
    verified_payload = verify_jwt(token, "my_super_secret")
    assert verified_payload is None

import pytest
import os
import base64
from app.core.helpers.crypto_helper import encrypt_value, decrypt_value
from app.core.settings import settings

def test_encrypt_decrypt_roundtrip(monkeypatch):
    plaintext = "super_secret_api_key_123!"
    
    class DummySecret:
        def __init__(self, val):
            self.val = val
        def get_secret_value(self):
            return base64.b64encode(self.val).decode('utf-8')
    monkeypatch.setattr(settings.security, "redis_encryption_key", DummySecret(os.urandom(32)))
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", None)
    
    ciphertext = encrypt_value(plaintext)
    assert ciphertext is not None
    assert ciphertext != plaintext
    
    decrypted = decrypt_value(ciphertext)
    assert decrypted == plaintext

def test_malformed_base64_input():
    assert decrypt_value("not_base64_!@#") is None

def test_payload_too_short():
    # Payload must be at least MAC + NONCE length (16+12=28 bytes)
    short_payload = base64.urlsafe_b64encode(b"short").decode('utf-8')
    assert decrypt_value(short_payload) is None

def test_key_rotation_fallback(monkeypatch):
    plaintext = "hello_world"
    old_key = os.urandom(32)
    new_key = os.urandom(32)
    
    # Set fake keys in settings
    class DummySecret:
        def __init__(self, val):
            self.val = val
        def get_secret_value(self):
            return base64.b64encode(self.val).decode('utf-8')
            
    monkeypatch.setattr(settings.security, "redis_encryption_key", DummySecret(old_key))
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", None)
    ciphertext_old = encrypt_value(plaintext)
    
    # Try decrypting with new key (fails, no fallback)
    monkeypatch.setattr(settings.security, "redis_encryption_key", DummySecret(new_key))
    assert decrypt_value(ciphertext_old) is None
    
    # Try decrypting with new key + fallback
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", DummySecret(old_key))
    assert decrypt_value(ciphertext_old) == plaintext

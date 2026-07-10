import pytest
import os
import base64
from app.core.settings import settings
from app.core.helpers.crypto_helper import encrypt_value, decrypt_value, _get_active_keys

# Mock settings securely for tests
class MockSecretStr:
    def __init__(self, value):
        self._value = value
    def get_secret_value(self):
        return self._value

@pytest.fixture(autouse=True)
def mock_keys(monkeypatch):
    # Set 32-byte keys
    key1 = base64.b64encode(os.urandom(32)).decode('utf-8')
    key2 = base64.b64encode(os.urandom(32)).decode('utf-8')
    
    monkeypatch.setattr(settings.security, "redis_encryption_key", MockSecretStr(key1))
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", MockSecretStr(key2))
    
def test_encrypt_decrypt_success():
    plaintext = "sk-ant-api03-very-secret-key"
    ciphertext = encrypt_value(plaintext)
    
    assert ciphertext is not None
    assert ciphertext != plaintext
    
    decrypted = decrypt_value(ciphertext)
    assert decrypted == plaintext

def test_decrypt_legacy_plaintext():
    plaintext = "sk-legacy-plaintext-key"
    # base64 decoding might fail, or it won't be long enough, or tag won't match
    decrypted = decrypt_value(plaintext)
    assert decrypted is None

def test_decrypt_tampered_ciphertext():
    plaintext = "my-secret-data"
    ciphertext = encrypt_value(plaintext)
    
    # Tamper with the ciphertext (change one character)
    tampered = ciphertext[:-1] + ('A' if ciphertext[-1] != 'A' else 'B')
    
    decrypted = decrypt_value(tampered)
    assert decrypted is None

def test_dual_key_fallback(monkeypatch):
    plaintext = "secret-fallback"
    
    # Generate keys
    old_key_bytes = os.urandom(32)
    new_key_bytes = os.urandom(32)
    
    # Set only old key to encrypt (simulating data encrypted BEFORE key rotation)
    monkeypatch.setattr(settings.security, "redis_encryption_key", MockSecretStr(base64.b64encode(old_key_bytes).decode('utf-8')))
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", None)
    
    ciphertext = encrypt_value(plaintext)
    
    # Now simulate key rotation: old key moves to old, new key becomes primary
    monkeypatch.setattr(settings.security, "redis_encryption_key", MockSecretStr(base64.b64encode(new_key_bytes).decode('utf-8')))
    monkeypatch.setattr(settings.security, "redis_encryption_old_key", MockSecretStr(base64.b64encode(old_key_bytes).decode('utf-8')))
    
    # Decrypt should still work using the old key
    decrypted = decrypt_value(ciphertext)
    assert decrypted == plaintext

def test_none_or_empty_values():
    assert encrypt_value(None) is None
    assert encrypt_value("") is None
    assert decrypt_value(None) is None
    assert decrypt_value("") is None

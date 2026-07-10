import base64
import os
import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from app.core.settings import settings
import app.core.logger as logger

log = logger.setup_app_logger("CryptoHelper")

def _get_active_keys():
    """Retrieve keys from settings and decode them. Returns a list of available keys (new_key, old_key)."""
    keys = []
    
    if settings.security.redis_encryption_key:
        try:
            k = settings.security.redis_encryption_key.get_secret_value()
            decoded = base64.b64decode(k)
            if len(decoded) != 32:
                log.warning(f"Encryption key must decode to exactly 32 bytes (got {len(decoded)}). Skipping.")
            else:
                keys.append(decoded)
        except Exception as e:
            log.warning(f"Failed to load new encryption key: {e}")
            
    if settings.security.redis_encryption_old_key:
        try:
            old_k = settings.security.redis_encryption_old_key.get_secret_value()
            decoded_old = base64.b64decode(old_k)
            if len(decoded_old) != 32:
                log.warning(f"Old encryption key must decode to exactly 32 bytes (got {len(decoded_old)}). Skipping.")
            else:
                keys.append(decoded_old)
        except Exception as e:
            log.warning(f"Failed to load old encryption key: {e}")
            
    return keys

def encrypt_value(plaintext: str) -> str | None:
    """
    Encrypts a plaintext string using AES-256-GCM.
    Uses settings.security.redis_encryption_key.
    Returns: base64(nonce + ciphertext + tag)
    """
    if not plaintext:
        return None
        
    keys = _get_active_keys()
    if not keys:
        log.warning("No encryption keys configured. Encryption failed.")
        return None

    primary_key = keys[0]
    
    try:
        # 96-bit nonce for GCM
        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(primary_key), modes.GCM(nonce))
        encryptor = cipher.encryptor()
        
        ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
        
        # tag is 16 bytes
        tag = encryptor.tag
        
        # Package: nonce (12) + ciphertext + tag (16)
        payload = nonce + ciphertext + tag
        return base64.b64encode(payload).decode('utf-8')
    except Exception as e:
        log.error(f"Encryption failed: {str(e)}")
        return None

def decrypt_value(ciphertext_b64: str) -> str | None:
    """
    Decrypts a base64 encoded AES-256-GCM payload.
    Tries the primary key, then falls back to the old key if available.
    Returns None if decryption fails (tampered, wrong key, or legacy plaintext).
    """
    if not ciphertext_b64:
        return None

    keys = _get_active_keys()
    if not keys:
        return None

    try:
        payload = base64.b64decode(ciphertext_b64)
    except binascii.Error:
        return None

    if len(payload) < 28:
        return None

    nonce = payload[:12]
    tag = payload[-16:]
    ciphertext = payload[12:-16]

    for key in keys:
        try:
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return plaintext.decode('utf-8')
        except Exception:
            continue
            
    return None

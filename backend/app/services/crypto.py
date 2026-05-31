"""Encryption and decryption for DB connection credentials."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..config import Settings

class CryptoError(Exception):
    """Raised when encryption or decryption fails."""
    pass

def _get_fernet(settings: Settings) -> Fernet:
    key = settings.db_encryption_key
    if not key:
        raise CryptoError("DB_ENCRYPTION_KEY is not configured")
    try:
        # Fernet requires a 32-byte base64-encoded key.
        # Ensure it's padded and valid.
        return Fernet(key.encode("utf-8"))
    except ValueError as e:
        raise CryptoError(f"Invalid DB_ENCRYPTION_KEY: {e}") from e

def encrypt(plaintext: str, settings: Settings) -> bytes:
    """Encrypt a plaintext string, returning raw bytes to store in the DB."""
    if not plaintext:
        return b""
    f = _get_fernet(settings)
    try:
        return f.encrypt(plaintext.encode("utf-8"))
    except Exception as e:
        raise CryptoError(f"Encryption failed: {e}") from e

def decrypt(ciphertext: bytes | str, settings: Settings) -> str:
    """Decrypt ciphertext bytes back to the original string."""
    if not ciphertext:
        return ""
    f = _get_fernet(settings)
    try:
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode("utf-8")
        return f.decrypt(ciphertext).decode("utf-8")
    except Exception as e:
        raise CryptoError(f"Decryption failed or invalid token: {e}") from e

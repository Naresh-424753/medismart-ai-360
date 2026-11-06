"""Encryption at rest for uploaded medical documents (Fernet / AES-128-CBC + HMAC)."""
import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _fernet() -> Fernet:
    key = settings.DATA_KEY
    if not key:
        # Dev fallback: derive a key from the JWT secret. Set DATA_KEY in production.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(data: bytes) -> bytes:
    return _fernet().decrypt(data)

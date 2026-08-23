"""
Token encryption helpers.

All Google OAuth tokens are encrypted with Fernet symmetric encryption before
being written to the database, and decrypted only when needed server-side.
Tokens are NEVER returned to the frontend in any API response.
"""

from cryptography.fernet import Fernet

from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_SECRET_KEY.encode())
    return _fernet


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns a URL-safe base64 string."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt an encrypted string back to plaintext."""
    return _get_fernet().decrypt(value.encode()).decode()

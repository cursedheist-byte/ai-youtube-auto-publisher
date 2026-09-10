"""
Symmetric encryption for OAuth tokens before they're written to the
database. Uses the ENCRYPTION_KEY env var (a Fernet key) so a raw DB leak
doesn't hand over usable YouTube access.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class TokenEncryptionError(Exception):
    pass


def _get_fernet() -> Fernet:
    if not settings.encryption_key:
        raise TokenEncryptionError(
            "ENCRYPTION_KEY is not set in the backend .env. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(settings.encryption_key.encode())
    except Exception as exc:
        raise TokenEncryptionError(f"ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_token(plain_text: str) -> str:
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    try:
        return _get_fernet().decrypt(cipher_text.encode()).decode()
    except InvalidToken as exc:
        raise TokenEncryptionError("Stored token could not be decrypted (wrong/rotated ENCRYPTION_KEY?).") from exc

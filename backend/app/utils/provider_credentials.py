"""Encryption and verification helpers for per-user provider credentials."""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_PREFIX = "enc:v1:"


def _cipher() -> Fernet:
    configured = settings.provider_credentials_key
    passphrase = configured.get_secret_value() if configured else settings.secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(passphrase.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_provider_credential(value: str) -> str:
    """Encrypt a provider credential for storage in an existing token column."""
    token = _cipher().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_provider_credential(value: str | None) -> str:
    """Decrypt a provider credential, rejecting plaintext values."""
    if not value or not value.startswith(_PREFIX):
        raise ValueError("Provider credential is missing or is not encrypted")
    try:
        return _cipher().decrypt(value.removeprefix(_PREFIX).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Provider credential could not be decrypted") from exc


def generate_webhook_secret() -> str:
    """Generate a connection-specific bearer secret shown only at creation/rotation."""
    return secrets.token_urlsafe(32)


def hash_webhook_secret(value: str) -> str:
    """Return a stable one-way digest suitable for constant-time verification."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_webhook_secret(value: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    return hmac.compare_digest(hash_webhook_secret(value), expected_hash)

from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.config import settings
from app.utils.provider_credentials import (
    decrypt_provider_credential,
    encrypt_provider_credential,
    generate_webhook_secret,
    hash_webhook_secret,
    verify_webhook_secret,
)


def test_provider_credential_round_trip_is_not_plaintext() -> None:
    with patch.object(settings, "provider_credentials_key", SecretStr("test-provider-key")):
        encrypted = encrypt_provider_credential("private-api-key")
        assert encrypted.startswith("enc:v1:")
        assert "private-api-key" not in encrypted
        assert decrypt_provider_credential(encrypted) == "private-api-key"


def test_plaintext_provider_credential_is_rejected() -> None:
    with pytest.raises(ValueError, match="not encrypted"):
        decrypt_provider_credential("private-api-key")


def test_webhook_secret_is_hashed_and_verified() -> None:
    secret = generate_webhook_secret()
    digest = hash_webhook_secret(secret)
    assert secret not in digest
    assert verify_webhook_secret(secret, digest)
    assert not verify_webhook_secret("wrong", digest)

"""Encrypted database credentials; the stable master key always stays outside the DB."""

import base64
import binascii
import json

from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from twf.brokers.contracts import BrokerFailure, Credentials
from twf.config.settings import Settings

ALGORITHM = "fernet-v1"


def unavailable() -> BrokerFailure:
    return BrokerFailure(
        "SECRET_STORE_UNAVAILABLE",
        "Saved credentials could not be decrypted. "
        "Check the credential master key or replace the credentials.",
        503,
    )


class CredentialCipher:
    """Fernet authenticates its version, timestamp, random IV and ciphertext together."""

    def __init__(self, settings: Settings) -> None:
        # Compatibility with existing Broker V1 records. Never try multiple keys or
        # silently generate a replacement. A configured new name takes precedence.
        key = settings.credential_master_key
        if key is None:
            key = settings.broker_secret_key
        if key is None or not key.get_secret_value():
            raise BrokerFailure(
                "SECRET_STORE_UNAVAILABLE",
                "Credential encryption key is not configured. "
                "Set TWF_CREDENTIAL_MASTER_KEY and restart TWF.",
                503,
            )
        try:
            encoded = key.get_secret_value().encode("ascii")
            decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded) != encoded:
                raise ValueError("Invalid key")
            self._cipher = Fernet(encoded)
        except (ValueError, UnicodeError, binascii.Error):
            raise BrokerFailure(
                "SECRET_STORE_UNAVAILABLE",
                "Credential encryption key is invalid. Set TWF_CREDENTIAL_MASTER_KEY "
                "to a URL-safe base64-encoded 32-byte key and restart TWF.",
                503,
            ) from None

    def encrypt(self, plaintext: bytes) -> str:
        # cryptography generates a fresh CSPRNG IV for every encrypt call. The IV
        # is persisted inside the standard token, never managed separately by TWF.
        return self._cipher.encrypt(plaintext).decode("ascii")

    def decrypt(self, payload: str, algorithm: str = ALGORITHM) -> bytes:
        if algorithm != ALGORITHM:
            raise unavailable()
        try:
            return self._cipher.decrypt(payload.encode("ascii"))
        except (InvalidToken, ValueError, UnicodeError):
            raise unavailable() from None


class EncryptedSecretStore:
    """Provider-neutral credential bundle, referenced by its owning broker account."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def cipher(self) -> CredentialCipher:
        return CredentialCipher(self.settings)

    def seal(self, value: Credentials) -> str:
        cipher = self.cipher()  # Fail closed before serializing any credentials.
        plaintext = json.dumps(
            {
                "api_key": value.api_key.get_secret_value(),
                "api_secret": value.api_secret.get_secret_value(),
                "access_token": value.access_token.get_secret_value()
                if value.access_token
                else None,
            }
        ).encode()
        return cipher.encrypt(plaintext)

    def open(self, ciphertext: str, algorithm: str = ALGORITHM) -> Credentials:
        try:
            return Credentials.model_validate_json(self.cipher().decrypt(ciphertext, algorithm))
        except (ValidationError, ValueError):
            raise unavailable() from None

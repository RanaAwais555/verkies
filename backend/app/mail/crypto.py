"""Mailbox passwords are encrypted at rest (SECURITY.md §5).

The key is derived from `VROS_SECRET_KEY` with HKDF, so the database alone never reveals a
password. Changing the secret key makes stored passwords unreadable: each person then reconnects
their mailbox, which VROS tells them instead of failing silently.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import Settings
from app.core.errors import ValidationFailed


def _fernet(settings: Settings) -> Fernet:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"vros-mailbox-credentials"
    ).derive(settings.signing_key)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def decrypt(settings: Settings, token: str) -> str:
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValidationFailed(
            "The stored mailbox password can no longer be read. Reconnect the mailbox.",
            code="mailbox_reconnect",
        ) from exc

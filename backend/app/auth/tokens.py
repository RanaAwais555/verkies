"""Random bearer tokens (sessions, invites, CSRF). Only keyed hashes are ever stored."""

import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str, key: bytes) -> str:
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def tokens_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())

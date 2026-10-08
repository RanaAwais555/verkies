"""Password hashing (Argon2id) and the password policy."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import ValidationFailed

MIN_LENGTH = 12
MAX_LENGTH = 256  # bounds hashing cost per request

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters

# Verified against when the email is unknown, so response time does not reveal which
# addresses have accounts.
_DUMMY_HASH = _hasher.hash("vros-timing-equaliser-not-a-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def check_password_policy(password: str, *, email: str) -> None:
    """Length is what matters most; also refuse passwords built from the user's own email."""
    if len(password) < MIN_LENGTH:
        raise ValidationFailed(f"Password must be at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        raise ValidationFailed(f"Password must be at most {MAX_LENGTH} characters.")
    if len(set(password)) < 4:
        raise ValidationFailed("Password is too repetitive.")
    local_part = email.split("@", 1)[0].casefold()
    if len(local_part) >= 4 and local_part in password.casefold():
        raise ValidationFailed("Password must not contain your email name.")

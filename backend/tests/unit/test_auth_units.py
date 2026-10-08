import uuid

import pytest

from app.auth.deps import cookie_names
from app.auth.passwords import check_password_policy, hash_password, verify_password
from app.auth.tokens import hash_token, new_token, tokens_match
from app.config import Settings
from app.core.errors import ValidationFailed
from app.core.ids import uuid7


def test_password_hash_round_trip() -> None:
    hashed = hash_password("a long enough passphrase")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a long enough passphrase")
    assert not verify_password(hashed, "a long enough passphrasE")


def test_verify_with_no_hash_is_false_but_still_hashes() -> None:
    assert verify_password(None, "anything at all") is False


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("short", "at least 12"),
        ("x" * 257, "at most 256"),
        ("aaaaaaaaaaaaaaaa", "repetitive"),
        ("my-ada.lovelace-password", "email name"),
    ],
)
def test_password_policy_rejects(password: str, message: str) -> None:
    with pytest.raises(ValidationFailed, match=message):
        check_password_policy(password, email="ada.lovelace@verkies.test")


def test_password_policy_accepts_a_passphrase() -> None:
    check_password_policy("correct horse battery staple", email="ada@verkies.test")


def test_tokens_are_random_and_hashed_with_key() -> None:
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert hash_token(a, b"k1") != hash_token(a, b"k2")
    assert hash_token(a, b"k1") == hash_token(a, b"k1")
    assert tokens_match(a, a) and not tokens_match(a, b)


def test_uuid7_is_version_7_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    timestamps = [i.int >> 80 for i in ids]
    assert timestamps == sorted(timestamps)
    assert len(set(ids)) == len(ids)


def test_cookies_use_host_prefix_only_over_https() -> None:
    plain = Settings(_env_file=None, public_url="http://localhost:3000")
    secure = Settings(_env_file=None, public_url="https://vros.example.com")
    assert cookie_names(plain) == ("vros_session", "vros_csrf")
    assert cookie_names(secure) == ("__Host-vros_session", "__Host-vros_csrf")


def test_signing_key_comes_from_secret_when_set() -> None:
    assert Settings(_env_file=None, secret_key="s" * 40).signing_key == b"s" * 40
    assert Settings(_env_file=None).signing_key  # development fallback exists

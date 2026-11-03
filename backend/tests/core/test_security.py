"""SEC-01 password hashing and SEC-10 token handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    password_policy_errors,
    verify_password,
)
from tests.conftest import TEST_SECRET, make_settings


@pytest.fixture
def cfg(tmp_path):
    return make_settings(tmp_path, tmp_path)


def test_password_hash_is_argon2id_and_not_plaintext() -> None:
    hashed = hash_password("Correct-Horse-9-Battery")
    assert hashed.startswith("$argon2id$")
    assert "Correct-Horse" not in hashed
    assert verify_password("Correct-Horse-9-Battery", hashed)
    assert not verify_password("wrong-password-1", hashed)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


@pytest.mark.parametrize(
    ("password", "fragment"),
    [("short1", "at least"), ("onlyletterspassword", "letter and one digit"), (" leading-space-123", "whitespace")],
)
def test_password_policy(password: str, fragment: str) -> None:
    assert any(fragment in error for error in password_policy_errors(password, min_length=12))


def test_password_policy_rejects_email_local_part() -> None:
    errors = password_policy_errors("alice-secure-123", min_length=12, email="alice@example.org")
    assert any("user name" in e for e in errors)


def test_access_token_round_trip(cfg) -> None:
    user_id = uuid.uuid4()
    token, expires = create_token(cfg, user_id=user_id, token_type="access", token_version=3, role="analyst")
    claims = decode_token(cfg, token, expected_type="access")
    assert claims.subject == user_id and claims.token_version == 3 and claims.role == "analyst"
    assert expires > datetime.now(UTC)


def test_token_type_confusion_rejected(cfg) -> None:
    refresh, _ = create_token(cfg, user_id=uuid.uuid4(), token_type="refresh", token_version=0)
    with pytest.raises(TokenError):
        decode_token(cfg, refresh, expected_type="access")


def test_expired_and_tampered_tokens_rejected(cfg) -> None:
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "tv": 0,
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
            "iss": cfg.jwt_issuer,
            "aud": cfg.jwt_audience,
            "jti": "x",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_token(cfg, expired, expected_type="access")
    token, _ = create_token(cfg, user_id=uuid.uuid4(), token_type="access", token_version=0)
    with pytest.raises(TokenError):
        decode_token(cfg, token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"), expected_type="access")


def test_alg_none_and_foreign_secret_rejected(cfg) -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "tv": 0,
        "iat": 0,
        "exp": 9999999999,
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "jti": "x",
    }
    unsigned = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(TokenError):
        decode_token(cfg, unsigned, expected_type="access")
    foreign = jwt.encode(payload, "another-secret-another-secret-123456", algorithm="HS256")
    with pytest.raises(TokenError):
        decode_token(cfg, foreign, expected_type="access")

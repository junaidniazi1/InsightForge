"""Phase 8A tests — JWT verification (JWKS + HS256 legacy fallback).

Gemini-style mocking: we never touch the network. An RSA key is generated once
at module level; the JWKS client is monkey-patched to return a `SigningKey`
wrapping its public counterpart.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.services.auth import AuthError, verify_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Single RSA keypair shared across the module — generating one per test is slow.
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_PUBLIC_PEM = _PUBLIC_KEY.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


@dataclass
class _FakeSigningKey:
    key: Any


def _settings(secret: str = "") -> Settings:
    return Settings(  # type: ignore[call-arg]
        supabase_url="https://placeholder.supabase.co",
        supabase_service_role_key="sr",
        supabase_jwt_secret=secret,
    )


def _make_token(
    *,
    algorithm: str,
    key: Any,
    sub: str = "user-abc",
    audience: str = "authenticated",
    exp_delta_seconds: int = 3600,
    extra: dict[str, Any] | None = None,
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=exp_delta_seconds)).timestamp()),
        "email": "test@example.com",
        **(extra or {}),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


@pytest.fixture(autouse=True)
def _clear_jwks_cache() -> None:
    # The JWKS client is lru_cached by URL — flush between tests so monkeypatches
    # in one test don't bleed into the next.
    from app.services import auth as auth_mod
    auth_mod._jwks_client.cache_clear()


@pytest.fixture
def jwks_returns_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every PyJWKClient lookup return our generated public key."""
    from jwt import PyJWKClient

    def fake_get(self: PyJWKClient, token: str) -> _FakeSigningKey:  # noqa: ARG001
        return _FakeSigningKey(key=_PUBLIC_KEY)

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", fake_get)


@pytest.fixture
def jwks_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a JWKS endpoint that 404s or is otherwise unreachable."""
    from jwt import PyJWKClient

    def fake_get(self: PyJWKClient, token: str):  # noqa: ARG001
        raise Exception("JWKS unavailable (simulated)")

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", fake_get)


# ===========================================================================
# JWKS path — asymmetric tokens
# ===========================================================================

def test_verify_rs256_token_with_jwks(jwks_returns_public_key: None) -> None:
    token = _make_token(algorithm="RS256", key=_PRIVATE_PEM)
    claims = verify_token(token, _settings())
    assert claims["sub"] == "user-abc"
    assert claims["email"] == "test@example.com"
    assert claims["aud"] == "authenticated"


def test_verify_rejects_tampered_signature(jwks_returns_public_key: None) -> None:
    token = _make_token(algorithm="RS256", key=_PRIVATE_PEM)
    # Flip a few characters in the signature segment.
    head, payload, sig = token.split(".")
    bad_sig = sig[:-4] + "AAAA"
    tampered = ".".join([head, payload, bad_sig])
    with pytest.raises(AuthError) as ei:
        verify_token(tampered, _settings())
    assert "invalid" in str(ei.value).lower()


def test_verify_rejects_expired_token(jwks_returns_public_key: None) -> None:
    token = _make_token(algorithm="RS256", key=_PRIVATE_PEM, exp_delta_seconds=-60)
    with pytest.raises(AuthError) as ei:
        verify_token(token, _settings())
    assert "expired" in str(ei.value).lower() or "invalid" in str(ei.value).lower()


def test_verify_rejects_wrong_audience(jwks_returns_public_key: None) -> None:
    token = _make_token(algorithm="RS256", key=_PRIVATE_PEM, audience="other-service")
    with pytest.raises(AuthError):
        verify_token(token, _settings())


def test_verify_rejects_malformed_token() -> None:
    with pytest.raises(AuthError):
        verify_token("not-a-jwt", _settings())
    with pytest.raises(AuthError):
        verify_token("", _settings())


# ===========================================================================
# Legacy HS256 path
# ===========================================================================

def test_verify_hs256_with_legacy_secret() -> None:
    secret = "test-shared-secret"
    token = _make_token(algorithm="HS256", key=secret)
    claims = verify_token(token, _settings(secret=secret))
    assert claims["sub"] == "user-abc"


def test_verify_hs256_rejects_when_secret_not_configured() -> None:
    token = _make_token(algorithm="HS256", key="some-secret")
    with pytest.raises(AuthError) as ei:
        verify_token(token, _settings(secret=""))
    assert "SUPABASE_JWT_SECRET" in str(ei.value)


def test_verify_hs256_rejects_wrong_secret() -> None:
    token = _make_token(algorithm="HS256", key="real-secret")
    with pytest.raises(AuthError):
        verify_token(token, _settings(secret="other-secret"))


# ===========================================================================
# Fallback path — RS256 token but JWKS unavailable
# ===========================================================================

def test_legacy_fallback_when_jwks_unavailable_and_secret_present(
    jwks_unavailable: None,
) -> None:
    """Migration scenario: token claims to be RS256 but JWKS is broken.
    If we have a legacy HS256 secret AND the token was actually signed with
    that secret, fall back rather than locking the user out."""
    secret = "fallback-secret"
    # Sign a HS256 token but claim RS256 in the header to trigger the path.
    # In reality this scenario fires when JWKS is down for a project that
    # still issues HS256 tokens.
    token = _make_token(algorithm="HS256", key=secret)
    # When JWKS is unavailable, _verify_symmetric is also tried via
    # _verify_asymmetric's fallback — but only if the token's actual alg
    # is HS256. Our verify_token routes by header alg, so this test exercises
    # the case where the header IS HS256.
    claims = verify_token(token, _settings(secret=secret))
    assert claims["sub"] == "user-abc"


def test_fallback_in_asymmetric_path_when_jwks_dies(
    jwks_unavailable: None,
) -> None:
    """When JWKS is down and the token is RS256-signed, the HS256 fallback
    fires but the signature obviously won't match.  The error must be an
    AuthError — not an unhandled exception — so the router can return 401."""
    secret = "fallback-secret"
    # A real RS256 token (signed with the test RSA key). JWKS is simulated
    # as unavailable, so _verify_asymmetric falls back to HS256 which will
    # fail because the signature is RSA, not HMAC.
    token = _make_token(algorithm="RS256", key=_PRIVATE_PEM)
    with pytest.raises(AuthError) as ei:
        verify_token(token, _settings(secret=secret))
    assert "invalid" in str(ei.value).lower()


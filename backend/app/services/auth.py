"""Supabase JWT verification with JWKS + legacy HS256 fallback.

Supabase has been migrating projects from a single shared HS256 signing secret
to per-project asymmetric (RS256 / ES256) keys served via JWKS. New projects
issue asymmetric tokens; legacy projects still issue symmetric ones. We support
both:

  - Token header `alg` says RS256 / ES256 → fetch the matching public key from
    the project's JWKS endpoint (cached + auto-refreshed by `PyJWKClient` on
    unknown `kid`).
  - Token header `alg` says HS256 → use `SUPABASE_JWT_SECRET` directly.

If a new-style token arrives but JWKS is unreachable (network blip, project
config issue), we log a warning and try the symmetric secret as a last resort
— matching the migration-period brief.

All failure modes raise `AuthError(message)`, which the router-level dependency
turns into HTTP 401.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from ..config import Settings

log = logging.getLogger(__name__)


_DEFAULT_AUDIENCE = "authenticated"
_ASYMMETRIC_ALGS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
_SYMMETRIC_ALGS = {"HS256", "HS384", "HS512"}


class AuthError(RuntimeError):
    """Raised whenever a token can't be verified. Mapped to 401 by the router."""


# ---------------------------------------------------------------------------
# JWKS client cache — keyed by URL so multiple Supabase projects (rare but
# possible in dev) each get their own client.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5.0)


def _jwks_url(supabase_url: str) -> str:
    return supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

def _unverified_alg(token: str) -> str | None:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return None
    alg = header.get("alg")
    return alg.upper() if isinstance(alg, str) else None


def _verify_asymmetric(token: str, alg: str, settings: Settings) -> dict[str, Any]:
    url = _jwks_url(settings.supabase_url)
    try:
        client = _jwks_client(url)
        signing_key = client.get_signing_key_from_jwt(token)
    except Exception as exc:  # noqa: BLE001 — JWKS errors are varied (network, 404, no kid match)
        # Legacy fallback: if the project hasn't actually rolled out asymmetric
        # keys yet, JWKS is empty or 404s. Try the shared secret if we have one.
        if settings.supabase_jwt_secret:
            log.warning(
                "JWKS lookup failed (%s) — falling back to symmetric HS256 secret. "
                "This is expected for legacy Supabase projects.",
                exc,
            )
            try:
                return jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience=_DEFAULT_AUDIENCE,
                )
            except jwt.PyJWTError as inner:
                raise AuthError(f"invalid token: {inner}") from inner
        raise AuthError(f"could not load JWKS for signature verification: {exc}") from exc

    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            audience=_DEFAULT_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc


def _verify_symmetric(token: str, alg: str, settings: Settings) -> dict[str, Any]:
    if not settings.supabase_jwt_secret:
        raise AuthError(
            "Token is signed with HS256 but SUPABASE_JWT_SECRET is not configured "
            "on the backend. New Supabase projects issue asymmetric (RS256) tokens "
            "— JWKS handles those automatically; legacy projects need the secret."
        )
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[alg],
            audience=_DEFAULT_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc


def verify_token(token: str, settings: Settings) -> dict[str, Any]:
    """Return decoded claims if the token is valid, else raise AuthError."""
    if not token:
        raise AuthError("missing token")

    alg = _unverified_alg(token)
    if alg is None:
        raise AuthError("token header is malformed")

    if alg in _ASYMMETRIC_ALGS:
        return _verify_asymmetric(token, alg, settings)
    if alg in _SYMMETRIC_ALGS:
        return _verify_symmetric(token, alg, settings)
    raise AuthError(f"unsupported token algorithm: {alg}")


__all__ = ["AuthError", "verify_token"]

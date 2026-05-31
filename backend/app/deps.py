"""Auth dependency: verifies a Supabase user JWT and returns the user id.

The verification logic — JWKS for new asymmetric tokens, HS256 fallback for
legacy projects — lives in `app.services.auth`. This module wraps it as a
FastAPI dependency so router signatures don't change.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings
from .services.auth import AuthError, verify_token


@dataclass
class CurrentUser:
    id: str
    email: str | None


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = verify_token(token, settings)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    return CurrentUser(id=user_id, email=payload.get("email"))

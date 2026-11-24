"""FastAPI dependency that resolves the authenticated user for every protected endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.local import InvalidToken, verify_token
from app.config import AuthMode, Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.models import User


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if settings.auth_mode is not AuthMode.local:
        # Supabase JWT verification lands in Outcome 10; refuse rather than guess.
        raise ApiError(503, "auth_unavailable", "Sign-in is not available on this server yet.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = verify_token(settings, token)
    except InvalidToken as exc:
        if exc.expired:
            raise ApiError(401, "session_expired", "Your session expired.") from exc
        raise ApiError(401, "invalid_session", "Your session is not valid.") from exc
    user = db.get(User, user_id)
    if user is None or user.auth_provider != "local":
        raise ApiError(401, "invalid_session", "Your session is not valid.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

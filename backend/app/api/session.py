"""Local development session endpoints (spec section 23)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.auth.local import issue_token
from app.config import AuthMode, Settings, get_settings
from app.db.base import new_id
from app.db.session import get_db
from app.errors import ApiError
from app.models import User

router = APIRouter(tags=["session"])


class SessionResponse(BaseModel):
    token: str
    user_id: str
    expires_at: datetime
    auth_mode: str


class MeResponse(BaseModel):
    user_id: str
    auth_provider: str
    created_at: datetime
    preferences: dict[str, Any]


DEFAULT_PREFERENCES: dict[str, Any] = {
    "mirror_default": True,
    "feedback_style": "encouraging",
    "retention": "keep_until_deleted",
}


@router.post("/api/session", response_model=SessionResponse, status_code=201)
def create_session(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    if settings.auth_mode is not AuthMode.local:
        raise ApiError(404, "not_found", "Local sessions are not available on this server.")
    user_id = new_id()
    user = User(
        id=user_id,
        auth_provider="local",
        auth_provider_id=user_id,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db.add(user)
    db.commit()
    return SessionResponse(
        token=issue_token(settings, user.id),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        auth_mode=settings.auth_mode.value,
    )


@router.get("/api/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        preferences=user.preferences,
    )

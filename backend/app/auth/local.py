"""Development/demo-only local sessions: a signed, expiring bearer token bound to a user row.

Never accepted when AUTH_MODE is not `local` (and production config forbids `local`).
"""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

_SALT = "adt-local-session-v1"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def issue_token(settings: Settings, user_id: str) -> str:
    return _serializer(settings).dumps({"uid": user_id})


class InvalidToken(Exception):
    def __init__(self, expired: bool) -> None:
        super().__init__("expired" if expired else "invalid")
        self.expired = expired


def verify_token(settings: Settings, token: str) -> str:
    try:
        data = _serializer(settings).loads(token, max_age=settings.session_ttl_seconds)
    except SignatureExpired as exc:
        raise InvalidToken(expired=True) from exc
    except BadSignature as exc:
        raise InvalidToken(expired=False) from exc
    if not isinstance(data, dict) or not isinstance(data.get("uid"), str):
        raise InvalidToken(expired=False)
    return str(data["uid"])

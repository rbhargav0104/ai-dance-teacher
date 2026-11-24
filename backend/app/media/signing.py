"""Short-lived signed media tokens. A `<video src>` can't send a bearer header, so the API
issues an expiring, owner-bound token per object after checking ownership (spec section 23)."""

from __future__ import annotations

from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

_SALT = "adt-media-v1"
MEDIA_TOKEN_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class MediaGrant:
    object_key: str
    user_id: str
    content_type: str


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def sign_media(settings: Settings, grant: MediaGrant) -> str:
    return _serializer(settings).dumps(
        {"k": grant.object_key, "u": grant.user_id, "t": grant.content_type}
    )


class InvalidMediaToken(Exception):
    def __init__(self, expired: bool) -> None:
        super().__init__("expired" if expired else "invalid")
        self.expired = expired


def verify_media(settings: Settings, token: str) -> MediaGrant:
    try:
        data = _serializer(settings).loads(token, max_age=MEDIA_TOKEN_TTL_SECONDS)
    except SignatureExpired as exc:
        raise InvalidMediaToken(expired=True) from exc
    except BadSignature as exc:
        raise InvalidMediaToken(expired=False) from exc
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in "kut"):
        raise InvalidMediaToken(expired=False)
    return MediaGrant(object_key=data["k"], user_id=data["u"], content_type=data["t"])

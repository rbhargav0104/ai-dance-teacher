from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer


def test_session_then_me(client: TestClient) -> None:
    res = client.post("/api/session")
    assert res.status_code == 201
    body = res.json()
    assert body["auth_mode"] == "local"
    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["user_id"] == body["user_id"]
    assert me.json()["preferences"]["mirror_default"] is True


def test_each_session_is_a_distinct_private_identity(client: TestClient) -> None:
    a = client.post("/api/session").json()
    b = client.post("/api/session").json()
    assert a["user_id"] != b["user_id"]


@pytest.mark.parametrize(
    ("header", "code"),
    [
        (None, "unauthenticated"),
        ("Basic abc", "unauthenticated"),
        ("Bearer garbage", "invalid_session"),
    ],
)
def test_me_rejects_bad_auth(client: TestClient, header: str | None, code: str) -> None:
    headers = {"Authorization": header} if header else {}
    res = client.get("/api/me", headers=headers)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == code


def test_token_signed_with_other_secret_rejected(client: TestClient) -> None:
    uid = client.post("/api/session").json()["user_id"]
    forged = URLSafeTimedSerializer("another-secret", salt="adt-local-session-v1").dumps(
        {"uid": uid}
    )
    res = client.get("/api/me", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


def test_expired_token_reports_session_expired(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    token = client.post("/api/session").json()["token"]
    monkeypatch.setattr(get_settings(), "session_ttl_seconds", -1)
    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "session_expired"


def test_local_sessions_refused_when_auth_mode_not_local(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import AuthMode, get_settings

    token = client.post("/api/session").json()["token"]
    monkeypatch.setattr(get_settings(), "auth_mode", AuthMode.supabase)
    assert client.post("/api/session").status_code == 404
    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 503

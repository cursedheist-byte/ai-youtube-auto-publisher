"""
Integration test simulating the exact browser journey:
login -> /oauth/start -> (Google) -> /oauth/callback -> GET /api/channels.
Google token exchange and YouTube API are mocked; everything else (DB, state,
cookies, redirect) runs for real so a swallowed callback failure can't hide.
"""
import os
import pathlib
import urllib.parse as up
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import User, YouTubeChannel
from app.services import youtube_oauth_service as svc

client = TestClient(app)
PROBE_CHANNEL = "UC_e2e_probe"


def _database_url_from_env_file():
    env_file = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


@pytest.fixture()
def real_db(monkeypatch):
    """Other test modules set a fake DATABASE_URL before app.config loads;
    pin the real database from backend/.env for this integration test."""
    import app.database as app_db
    url = _database_url_from_env_file()
    assert url, "backend/.env must define DATABASE_URL for the integration test"
    engine = create_engine(url, pool_pre_ping=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(app_db, "SessionLocal", Session)
    monkeypatch.setattr(app_db, "engine", engine)
    yield Session
    engine.dispose()


def _make_test_user(real_db=None):
    """Create a throwaway user for this test (password hashed properly via API)."""
    import uuid
    email = f"e2e-oauth-{uuid.uuid4().hex[:8]}@example.com"
    password = "test-password-123"
    res = client.post("/api/auth/register", json={"email": email, "password": password})
    assert res.status_code == 201, res.text
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_full_oauth_flow_connects_channel_and_lists_it(real_db):
    SessionLocal = real_db
    with SessionLocal() as db:
        probe_ids = [c.id for c in db.query(YouTubeChannel).filter(YouTubeChannel.youtube_channel_id == PROBE_CHANNEL)]
        if probe_ids:
            from app.models import AutomationSettings
            db.query(AutomationSettings).filter(AutomationSettings.channel_id.in_(probe_ids)).delete(synchronize_session=False)
            db.query(YouTubeChannel).filter(YouTubeChannel.id.in_(probe_ids)).delete(synchronize_session=False)
            db.commit()

    token = _make_test_user()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email.endswith("@example.com")).order_by(User.created_at.desc()).first()
        user_id = str(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    # Same requirement as production: the initiating user must have a usable
    # OAuth client configured (own-credentials mode).
    fake_client = ("cid", "cs", "or-key")

    # --- 1. start: identity bound to user, cookies set ---
    with patch.object(svc, "credential_values", return_value=fake_client):
        res = client.get("/api/channels/oauth/start", headers=headers, params={"return_to": "/app"})
    assert res.status_code == 200, res.text
    auth_url = res.json()["authorization_url"]
    assert "accounts.google.com" in auth_url
    cookie_names = {c.name for c in res.cookies.jar}
    assert any(n.startswith("yt_oauth_state_binding") for n in cookie_names), cookie_names
    state = up.parse_qs(up.urlsplit(auth_url).query)["state"][0]

    # --- 2. callback: exchange + store (Google parts mocked) ---
    fake_creds = Credentials(
        token="tok", refresh_token="ref", token_uri="https://oauth2.googleapis.com/token",
        client_id="cid", client_secret="cs",
    )
    with patch("app.routers.channels.exchange_code_for_credentials", return_value=fake_creds), \
         patch("app.routers.channels.fetch_channel_info", return_value={"id": PROBE_CHANNEL, "title": "E2E Probe"}), \
         patch("app.services.youtube_oauth_service.encrypt_token", side_effect=lambda v: "enc_" + v), \
         patch.object(svc, "credential_values", return_value=fake_client):
        res = client.get(
            "/api/channels/oauth/callback",
            params={"code": "authcode", "state": state},
            follow_redirects=False,
        )
    assert res.status_code == 307, res.text
    location = res.headers["location"]
    assert "channel_connected=1" in location, f"expected success redirect, got: {location}"
    assert "channel_error" not in location

    # --- 3. the row must actually be committed for this user ---
    with SessionLocal() as db:
        row = db.query(YouTubeChannel).filter(YouTubeChannel.youtube_channel_id == PROBE_CHANNEL).one_or_none()
        assert row is not None, "channel row must be committed"
        assert str(row.user_id) == user_id
        assert row.status.value == "connected"

    # --- 4. GET /api/channels must return it ---
    res = client.get("/api/channels", headers=headers)
    assert res.status_code == 200, res.text
    listed = [c["channel"]["youtube_channel_id"] for c in res.json()]
    assert PROBE_CHANNEL in listed, f"probe channel missing from listing: {listed}"


def test_callback_failure_is_visible_in_redirect(real_db):
    SessionLocal = real_db
    token = _make_test_user()
    headers = {"Authorization": f"Bearer {token}"}
    with patch.object(svc, "credential_values", return_value=("cid", "cs", "or-key")):
        res = client.get("/api/channels/oauth/start", headers=headers, params={"return_to": "/app"})
    assert res.status_code == 200
    res = client.get(
        "/api/channels/oauth/callback",
        params={"code": "x", "state": "bogus-state"},
        follow_redirects=False,
    )
    assert res.status_code == 307
    assert "channel_error=" in res.headers["location"]
def test_state_cookie_is_secure_and_samesite_none_on_https(real_db):
    """Regression: in production the SPA calls the API cross-site, so the
    browser-binding cookie must be Secure + SameSite=None, otherwise browsers
    drop the third-party Set-Cookie and the callback fails the state check."""
    token = _make_test_user(real_db)
    headers = {"Authorization": f"Bearer {token}", "x-forwarded-proto": "https"}
    with patch.object(svc, "credential_values", return_value=("cid", "cs", "or-key")):
        res = client.get(
            "/api/channels/oauth/start",
            headers=headers,
            params={"return_to": "/app"},
        )
    assert res.status_code == 200, res.text
    set_cookie = res.headers.get("set-cookie", "")
    assert "yt_oauth_state_binding=" in set_cookie
    assert "Secure" in set_cookie, set_cookie
    assert "SameSite=none" in set_cookie, set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/channels/oauth" in set_cookie

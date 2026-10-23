from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import ConfigError
from app.main import create_app
from app.models import User
from tests.conftest import add_topic, login, vote

GOOGLE_METADATA = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}


# ---------- Protected endpoints ----------


def test_unauthenticated_topic_create_rejected(client):
    response = client.post("/api/topics", json={"name": "Rust"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


def test_unauthenticated_vote_rejected(client, other_client):
    token = login(client)
    topic = add_topic(client, token, "Rust").json()
    assert other_client.post(f"/api/topics/{topic['id']}/vote").status_code == 401


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401
    login(client, "Ada")
    body = client.get("/api/me").json()
    assert body["user"]["name"] == "Ada"
    assert body["csrf_token"]


def test_index_redirects_to_login_when_signed_out(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_index_and_login_pages_when_signed_in(client):
    login(client)
    assert client.get("/", follow_redirects=False).status_code == 200
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_logout_clears_session(client):
    token = login(client)
    assert client.post("/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204
    assert client.get("/api/me").status_code == 401


# ---------- CSRF ----------


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Token": "wrong"}])
def test_writes_require_csrf_token(client, headers):
    token = login(client)
    topic = add_topic(client, token, "Rust").json()

    assert client.post("/api/topics", json={"name": "Go"}, headers=headers).status_code == 403
    assert client.post(f"/api/topics/{topic['id']}/vote", headers=headers).status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 403


def test_csrf_token_rotates_on_login(client):
    before = client.get("/auth/options").json()["csrf_token"]
    after = login(client)
    assert before != after
    # The pre-login token is no longer accepted.
    assert add_topic(client, before, "Rust").status_code == 403


def test_dev_login_requires_csrf(client):
    response = client.post("/auth/dev-login", json={"name": "Ada"})
    assert response.status_code == 403


# ---------- Development-only sign-in ----------


def test_dev_login_rejects_empty_name(client):
    token = client.get("/auth/options").json()["csrf_token"]
    response = client.post("/auth/dev-login", json={"name": "  "}, headers={"X-CSRF-Token": token})
    assert response.status_code == 422


def test_dev_login_reuses_user(client, other_client, db):
    login(client, "Ada")
    login(other_client, "ada")
    assert len(db.scalars(select(User)).all()) == 1


def test_dev_login_not_registered_when_disabled(make_settings):
    app = create_app(make_settings(dev_auth_enabled=False))
    with TestClient(app) as client:
        token = client.get("/auth/options").json()["csrf_token"]
        response = client.post("/auth/dev-login", json={"name": "Ada"}, headers={"X-CSRF-Token": token})
        assert response.status_code == 404
        assert client.get("/auth/options").json()["dev_login_enabled"] is False


def test_production_refuses_dev_auth(make_settings):
    settings = make_settings(
        app_env="production",
        dev_auth_enabled=True,
        google_client_id="id",
        google_client_secret="secret",
    )
    with pytest.raises(ConfigError, match="DEV_AUTH_ENABLED"):
        create_app(settings)


def test_production_without_dev_auth_has_no_dev_login(make_settings):
    settings = make_settings(
        app_env="production",
        dev_auth_enabled=False,
        google_client_id="id",
        google_client_secret="secret",
    )
    # Production cookies are Secure-only, so talk to the app over https.
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        token = client.get("/auth/options").json()["csrf_token"]
        response = client.post("/auth/dev-login", json={"name": "Ada"}, headers={"X-CSRF-Token": token})
        assert response.status_code == 404
        assert client.get("/docs").status_code == 404


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"secret_key": ""}, "SECRET_KEY is required"),
        ({"app_env": "staging"}, "APP_ENV must be one of"),
        ({"app_env": "production", "dev_auth_enabled": False, "secret_key": "short",
          "google_client_id": "id", "google_client_secret": "s"}, "at least 32 characters"),
        ({"app_env": "production", "dev_auth_enabled": False}, "GOOGLE_CLIENT_ID"),
    ],
)
def test_invalid_configuration_rejected(make_settings, overrides, message):
    with pytest.raises(ConfigError, match=message):
        create_app(make_settings(**overrides))


# ---------- Google OAuth ----------


@pytest.fixture
def google_app(make_settings, monkeypatch):
    app = create_app(make_settings(
        dev_auth_enabled=False,
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_client_secret="test-client-secret",
    ))

    async def fake_metadata():
        return GOOGLE_METADATA

    # Avoid network discovery; everything else runs through Authlib for real.
    monkeypatch.setattr(app.state.oauth.google, "load_server_metadata", fake_metadata)
    return app


def test_google_login_unconfigured_returns_503(client):
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 503
    assert client.get("/auth/options").json()["google_enabled"] is False


def test_google_login_redirects_with_state_nonce_and_pkce(google_app):
    with TestClient(google_app) as client:
        response = client.get("/auth/google", follow_redirects=False)
        assert response.status_code == 302

        location = urlparse(response.headers["location"])
        params = parse_qs(location.query)
        assert f"{location.scheme}://{location.netloc}{location.path}" == GOOGLE_METADATA["authorization_endpoint"]
        assert params["client_id"] == ["test-client-id.apps.googleusercontent.com"]
        assert params["redirect_uri"] == ["http://testserver/auth/callback"]
        assert params["response_type"] == ["code"]
        assert set(params["scope"][0].split()) == {"openid", "email", "profile"}
        assert params["state"][0]
        assert params["nonce"][0]
        assert params["code_challenge_method"] == ["S256"]


@pytest.mark.parametrize("query", ["", "?code=abc", "?code=abc&state=forged"])
def test_google_callback_rejects_missing_or_unknown_state(google_app, query):
    with TestClient(google_app) as client:
        client.get("/auth/google", follow_redirects=False)  # creates a real pending state
        response = client.get(f"/auth/callback{query}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login?error=google"
        assert client.get("/api/me").status_code == 401


def test_google_callback_reports_provider_error(google_app):
    with TestClient(google_app) as client:
        response = client.get("/auth/callback?error=access_denied", follow_redirects=False)
        assert response.headers["location"] == "/login?error=google"


def _fake_token(monkeypatch, app, claims):
    async def fake_authorize_access_token(request, **kwargs):
        return {"access_token": "x", "userinfo": claims}

    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_authorize_access_token)


def test_google_callback_signs_user_in(google_app, monkeypatch):
    _fake_token(monkeypatch, google_app, {
        "sub": "1234567890",
        "email": "ada@example.com",
        "email_verified": True,
        "name": "Ada Lovelace",
    })
    with TestClient(google_app) as client:
        response = client.get("/auth/callback?code=abc&state=xyz", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

        me = client.get("/api/me").json()
        assert me["user"] == {"id": me["user"]["id"], "name": "Ada Lovelace", "email": "ada@example.com"}

        # The authenticated Google user can create and vote.
        topic = add_topic(client, me["csrf_token"], "Category theory").json()
        assert vote(client, me["csrf_token"], topic["id"]).status_code == 201

        session = google_app.state.session_factory()
        try:
            user = session.scalar(select(User))
            assert user.subject == "1234567890"
        finally:
            session.close()


def test_google_callback_rejects_unverified_email(google_app, monkeypatch):
    _fake_token(monkeypatch, google_app, {
        "sub": "1234567890",
        "email": "ada@example.com",
        "email_verified": False,
        "name": "Ada",
    })
    with TestClient(google_app) as client:
        response = client.get("/auth/callback?code=abc&state=xyz", follow_redirects=False)
        assert response.headers["location"] == "/login?error=unverified"
        assert client.get("/api/me").status_code == 401


def test_session_cookie_flags(make_settings):
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.get("/auth/options")
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie


def test_security_headers(client):
    response = client.get("/auth/options")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

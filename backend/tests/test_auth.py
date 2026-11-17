"""Tests for Google Sign-In verification.

We cannot mint a real Google-signed token in a test, and we must not reach the
network. So `id_token.verify_oauth2_token` -- the one call that does the
cryptography -- is replaced with a stub, and these tests cover everything
around it: the header parsing, the REQUIRE_AUTH switch, the email_verified
check, the allowlist, and the error codes.

What is deliberately NOT tested here: that Google's signature check works.
That is google-auth's job and it has its own test suite. What matters is that
we call it with our own client id as the audience, which test_audience_is_our
_client_id pins down.
"""

import pytest
from fastapi.testclient import TestClient

from api import auth, main

CLAIMS = {
    "sub": "1234567890",
    "email": "Student@Gmail.com",
    "email_verified": True,
    "name": "A Student",
    "picture": "https://example.test/p.jpg",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts with auth unconfigured, and sets what it needs."""
    for name in ("GOOGLE_CLIENT_ID", "REQUIRE_AUTH", "ALLOWED_EMAILS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client():
    return TestClient(main.app, raise_server_exceptions=False)


def stub_verify(monkeypatch, claims=None, error=None):
    """Replace the cryptographic check with a predictable stand-in."""
    calls = {}

    def fake(token, request, audience):
        calls["token"] = token
        calls["audience"] = audience
        if error:
            raise ValueError(error)
        return claims if claims is not None else CLAIMS

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake)
    return calls


# ---------------------------------------------------------------- the switch

def test_anonymous_is_allowed_when_auth_is_off(client):
    """Local development and the static build must keep working."""
    assert client.get("/api/jobs").status_code == 200


def test_anonymous_is_refused_when_auth_is_required(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    response = client.get("/api/jobs")
    assert response.status_code == 401
    assert response.json()["detail"] == "sign in required"


def test_every_data_endpoint_is_protected(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    for path in ("/api/jobs", "/api/jobs/anything", "/api/meta", "/api/me"):
        assert client.get(path).status_code == 401, path


def test_health_stays_open_so_the_host_can_probe_it(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    assert client.get("/api/health").status_code == 200


def test_auth_config_stays_open_so_the_login_page_can_load(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    body = client.get("/api/auth/config").json()
    assert body == {"configured": True, "required": True}


def test_auth_config_reports_when_unconfigured(client):
    assert client.get("/api/auth/config").json() == {"configured": False, "required": False}


# ---------------------------------------------------------------- verifying

def test_a_valid_token_identifies_the_user(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    stub_verify(monkeypatch)

    body = client.get("/api/me", headers={"Authorization": "Bearer good.token.here"}).json()
    assert body["email"] == "student@gmail.com"  # normalised to lower case
    assert body["name"] == "A Student"
    assert body["sub"] == "1234567890"


def test_audience_is_our_client_id(client, monkeypatch):
    """The audience check is what stops a token minted for another app working.

    If this ever regressed, any Google app's token would be accepted here, so
    it is worth asserting explicitly rather than trusting the call site.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "ours.apps.googleusercontent.com")
    calls = stub_verify(monkeypatch)

    client.get("/api/me", headers={"Authorization": "Bearer t"})
    assert calls["audience"] == "ours.apps.googleusercontent.com"
    assert calls["token"] == "t"


def test_a_rejected_token_is_401(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    stub_verify(monkeypatch, error="Token expired")

    response = client.get("/api/me", headers={"Authorization": "Bearer stale"})
    assert response.status_code == 401
    assert "Token expired" in response.json()["detail"]


def test_an_unverified_email_is_refused(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    stub_verify(monkeypatch, claims={**CLAIMS, "email_verified": False})

    response = client.get("/api/me", headers={"Authorization": "Bearer t"})
    assert response.status_code == 403
    assert "not verified" in response.json()["detail"]


def test_a_token_cannot_be_verified_without_a_client_id(client, monkeypatch):
    stub_verify(monkeypatch)
    response = client.get("/api/me", headers={"Authorization": "Bearer t"})
    assert response.status_code == 503
    assert "GOOGLE_CLIENT_ID" in response.json()["detail"]


# ---------------------------------------------------------------- allowlist

def test_allowlist_lets_a_listed_address_in(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("ALLOWED_EMAILS", "student@gmail.com, someone@else.com")
    stub_verify(monkeypatch)

    assert client.get("/api/me", headers={"Authorization": "Bearer t"}).status_code == 200


def test_allowlist_keeps_everyone_else_out(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("ALLOWED_EMAILS", "only@me.com")
    stub_verify(monkeypatch)

    response = client.get("/api/me", headers={"Authorization": "Bearer t"})
    assert response.status_code == 403
    assert "allowlist" in response.json()["detail"]


def test_no_allowlist_means_any_google_account(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    stub_verify(monkeypatch)
    assert client.get("/api/me", headers={"Authorization": "Bearer t"}).status_code == 200


# ---------------------------------------------------------------- the header

@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abc", "token abc", "abc"],
)
def test_a_malformed_authorization_header_is_treated_as_anonymous(client, monkeypatch, header):
    """Anything that is not "Bearer <token>" must not be half-accepted."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    response = client.get("/api/jobs", headers={"Authorization": header} if header else {})
    assert response.status_code == 401


def test_bearer_is_case_insensitive(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    stub_verify(monkeypatch)
    assert client.get("/api/me", headers={"Authorization": "bearer t"}).status_code == 200


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_require_auth_accepts_the_usual_truthy_spellings(monkeypatch, value):
    monkeypatch.setenv("REQUIRE_AUTH", value)
    assert auth.auth_required() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
def test_require_auth_is_off_for_anything_else(monkeypatch, value):
    monkeypatch.setenv("REQUIRE_AUTH", value)
    assert auth.auth_required() is False

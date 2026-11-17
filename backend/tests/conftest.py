"""Fixtures shared by every test file.

api/main.py reads backend/.env at import time, so that a developer's local
GOOGLE_CLIENT_ID and REQUIRE_AUTH work without exporting anything by hand.

That file must never decide whether the tests pass. CI has no .env, so a suite
that depended on one would behave differently on the two machines -- and the
direction of that difference is the dangerous kind: with REQUIRE_AUTH=true set
locally, every API test 401s at home and passes in CI, which is how you end up
trusting a green pipeline over a red terminal.

So: clear the auth settings before every test. The tests that care about them
set them explicitly with monkeypatch.
"""

import pytest

AUTH_ENV = ("GOOGLE_CLIENT_ID", "REQUIRE_AUTH", "ALLOWED_EMAILS")


@pytest.fixture(autouse=True)
def isolate_auth_env(monkeypatch):
    for name in AUTH_ENV:
        monkeypatch.delenv(name, raising=False)

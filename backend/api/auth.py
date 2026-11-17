"""Google Sign-In verification.

The browser never sends us a password. It runs Google's own sign-in flow, gets
back an ID token (a JWT signed by Google), and sends that in the
Authorization header. This module checks the token is genuine.

Why it is done this way and not with a username and password field:

  - Asking for someone's Gmail password in our own form is phishing. Google
    blocks it, and it would hand us a credential we have no business holding.
  - With Sign-In, Google shows its own password screen. We only ever see a
    signed assertion that says "this email proved who they are, for your app,
    at this time".

What verify() actually checks, via google-auth:

  - the RS256 signature against Google's published public keys (fetched from
    Google and cached, so a rotated key is picked up automatically)
  - `aud` equals our own client id -- without this, a token minted for any
    other Google app would be accepted here
  - `iss` is accounts.google.com
  - `exp` has not passed

That list is the reason this is real authentication and not decoration: none of
it can be faked by the browser, because the browser does not have Google's
signing key.

The one thing to be honest about: this protects the API. It cannot protect the
statically published dataset on GitHub Pages, which is a public file by
definition. See README.
"""

import os

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Reused across requests so Google's certificates are fetched once and cached
# rather than on every verification.
_request = google_requests.Request()


def client_id() -> str:
    """The OAuth client id this server will accept tokens for."""
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def auth_required() -> bool:
    """Whether endpoints refuse anonymous callers.

    Off by default so local development and the tests do not need tokens.
    The deployed API turns it on with REQUIRE_AUTH=true.
    """
    return os.environ.get("REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes")


def _allowed_emails() -> set[str]:
    """Optional allowlist. Empty means any Google account may sign in.

    Worth knowing: without this, anyone with a Google account can sign in.
    That is usually what you want for a public job board; set
    ALLOWED_EMAILS=a@x.com,b@y.com to lock it to specific people.
    """
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def verify(token: str) -> dict:
    """Check a Google ID token and return the claims we care about."""
    configured = client_id()
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_CLIENT_ID is not set on the server, so tokens cannot be verified.",
        )

    try:
        claims = id_token.verify_oauth2_token(token, _request, configured)
    except ValueError as exc:
        # google-auth raises ValueError for a bad signature, wrong audience,
        # wrong issuer and expiry alike. All of them mean the same thing here.
        raise HTTPException(status_code=401, detail=f"invalid Google token: {exc}") from exc

    email = (claims.get("email") or "").lower()

    # A Google account can carry an unverified address. Treating one as proof
    # of identity would be a hole, so refuse it.
    if not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="this Google account's email is not verified")

    allowed = _allowed_emails()
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="this account is not on the allowlist")

    return {
        "sub": claims.get("sub"),
        "email": email,
        "name": claims.get("name") or email,
        "picture": claims.get("picture"),
    }


def current_user(authorization: str = Header(default="")) -> dict | None:
    """FastAPI dependency: the signed-in user, or None when anonymous.

    Raises 401 for an anonymous caller only when REQUIRE_AUTH is on, so the
    same code serves an open API locally and a closed one in production.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        if auth_required():
            raise HTTPException(status_code=401, detail="sign in required")
        return None

    return verify(token.strip())

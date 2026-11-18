"""Smoke-test a deployed API.

    python scripts/check_api.py https://your-service.onrender.com
    python scripts/check_api.py http://127.0.0.1:8000 --origin http://localhost:5173

Checks what actually matters about a deployment: that it is serving the data,
that authentication is switched on and cannot be bypassed, and that the browser
origin you are going to call it from is allowed through CORS.

Exits non-zero if anything fails, so it can gate a deploy.

On a free host the first request can take about a minute while the service
wakes up, which is why the timeout is generous and the first check reports how
long it waited.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 90

passed = 0
failed = 0


def report(ok, label, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  -> {detail}" if detail else ""))


def request(url, method="GET", headers=None):
    """Return (status, body-as-dict-or-text, headers). Never raises for 4xx/5xx."""
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            status, head = r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status, head = e.code, dict(e.headers)
    except Exception as e:  # DNS failure, refused connection, timeout
        return None, str(e), {}
    try:
        return status, json.loads(raw), head
    except json.JSONDecodeError:
        return status, raw, head


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", help="e.g. https://your-service.onrender.com")
    parser.add_argument(
        "--origin",
        default="",
        help="browser origin to test CORS for, e.g. https://you.github.io",
    )
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Checking {base}\n")

    # ---- reachable, and serving data -------------------------------------
    started = time.time()
    status, body, _ = request(f"{base}/api/health")
    waited = time.time() - started

    if status is None:
        report(False, "service reachable", body)
        print("\nCould not reach the service at all. Check the URL.")
        return 1

    report(status == 200, "/api/health responds 200", f"{status}, {waited:.1f}s")
    jobs = body.get("jobs") if isinstance(body, dict) else None
    report(bool(jobs), "serving the job dataset", f"{jobs} jobs")
    report(
        isinstance(body, dict) and bool(body.get("last_refreshed")),
        "knows when the data was last refreshed",
        body.get("last_refreshed") if isinstance(body, dict) else "",
    )

    # ---- authentication ---------------------------------------------------
    status, cfg, _ = request(f"{base}/api/auth/config")
    report(status == 200, "/api/auth/config is public", str(status))
    configured = isinstance(cfg, dict) and cfg.get("configured")
    required = isinstance(cfg, dict) and cfg.get("required")
    report(bool(configured), "GOOGLE_CLIENT_ID is set on the server")
    report(bool(required), "REQUIRE_AUTH is on", str(cfg))

    print()
    for path in ("/api/jobs", "/api/meta", "/api/jobs/anything", "/api/me"):
        status, body, _ = request(f"{base}{path}")
        if required:
            detail = body.get("detail") if isinstance(body, dict) else ""
            report(status == 401, f"{path} refuses anonymous callers", f"{status} {detail}")
        else:
            report(status == 200, f"{path} serves data (auth off)", str(status))

    print()
    status, body, _ = request(
        f"{base}/api/me",
        headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.forged"},
    )
    detail = body.get("detail", "") if isinstance(body, dict) else str(body)
    report(status in (401, 403), "a forged token is rejected", f"{status} {detail[:70]}")

    status, _, _ = request(f"{base}/api/jobs", headers={"Authorization": "Bearer "})
    report(status == 401, "an empty bearer token is not accepted", str(status))

    # ---- CORS -------------------------------------------------------------
    if args.origin:
        print()
        status, _, head = request(
            f"{base}/api/jobs",
            method="OPTIONS",
            headers={
                "Origin": args.origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        allow = head.get("access-control-allow-origin") or head.get(
            "Access-Control-Allow-Origin", ""
        )
        report(allow == args.origin, f"CORS allows {args.origin}", allow or "no header")

        allow_headers = (
            head.get("access-control-allow-headers")
            or head.get("Access-Control-Allow-Headers", "")
        ).lower()
        report(
            "authorization" in allow_headers,
            "CORS allows the Authorization header",
            allow_headers or "no header",
        )

        _, _, head = request(
            f"{base}/api/jobs",
            method="OPTIONS",
            headers={"Origin": "https://not-allowed.example", "Access-Control-Request-Method": "GET"},
        )
        rogue = head.get("access-control-allow-origin") or head.get(
            "Access-Control-Allow-Origin", ""
        )
        report(not rogue, "CORS refuses an unlisted origin", rogue or "no header, correct")

    # ---- docs -------------------------------------------------------------
    print()
    status, _, _ = request(f"{base}/docs")
    report(status == 200, "/docs (interactive API docs) is up", str(status))

    print(f"\n{passed} passed, {failed} failed")
    if failed == 0:
        print("\nDeployment looks correct.")
        if args.origin:
            print(f"Point the frontend at: {base}/api")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

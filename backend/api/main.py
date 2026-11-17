"""Read-only HTTP API over the files the pipeline writes.

    uvicorn api.main:app --reload --port 8000

Why this exists: the pipeline produces data/jobs.json once a day. This serves
it as a real search API so the frontend asks the server for a page of results
instead of downloading every post and filtering in the browser.

Why it is still only files, with no database: 565 posts is small enough that
filtering a list of dicts takes about a millisecond. A database would add a
service to run, a schema to migrate and a connection to pool, and would not
make a single request faster at this size. If the dataset reached six figures,
this is the file to change -- swap _load() for a query and keep the routes.

The file is re-read when its modification time changes, so a pipeline run
shows up without restarting the server.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.auth import auth_required, client_id, current_user
from pipeline.config import data_path

app = FastAPI(
    title="Beep fresher jobs API",
    description="Fresher jobs and internships in India, collected from public job-board APIs.",
    version="1.0.0",
)

# The browser calls this from a different origin in development (Vite on 5173,
# API on 8000), so the API has to say that is allowed. In production the list
# comes from an env var, because the deployed frontend's URL is not known here.
default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------- loading

# Module-level cache. Keyed on the file's mtime so we reload only on change.
_cache = {"jobs": [], "by_id": {}, "meta": {}, "mtime": None, "loaded_at": None}

SNIPPET_CHARS = 300


def _parse_time(value):
    """ISO string -> aware datetime, or None.

    jobs.json carries three shapes: "...Z", "...+05:30" and one with
    microseconds. fromisoformat handles all three on Python 3.11+, but it does
    not accept a bare "Z", so swap that for the explicit offset first.
    Sorting these as plain strings would put "+05:30" in the wrong place,
    which is why every comparison below goes through a real datetime.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load():
    """Return the in-memory job list, reloading if jobs.json changed on disk."""
    path = data_path("jobs")
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="data/jobs.json is missing. Run: python -m pipeline.run",
        )

    mtime = path.stat().st_mtime
    if _cache["mtime"] == mtime:
        return _cache["jobs"]

    jobs = json.loads(path.read_text(encoding="utf-8"))

    for job in jobs:
        # Internal fields start with "_" and are stripped before any response.
        # Precomputed once here rather than on every request.
        posted = _parse_time(job.get("posted_at"))
        job["_posted"] = posted
        job["_haystack"] = " ".join(
            str(job.get(f) or "") for f in ("title", "company", "raw_location")
        ).lower()

    meta_path = data_path("run_meta")
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # run_meta is informational. A broken one must not take the API down.
            meta = {}

    _cache.update(
        jobs=jobs,
        by_id={job["id"]: job for job in jobs},
        meta=meta,
        mtime=mtime,
        loaded_at=datetime.now(timezone.utc).isoformat(),
    )
    return jobs


def public(job, full_description=False):
    """Strip internal fields, and trim the description unless it was asked for.

    The list endpoint sends a 300-character snippet instead of the full 1200,
    which is about a third of the payload for a page of results. The detail
    endpoint sends the whole thing.
    """
    out = {k: v for k, v in job.items() if not k.startswith("_")}
    description = out.get("description") or ""
    if not full_description and len(description) > SNIPPET_CHARS:
        out["description"] = description[:SNIPPET_CHARS].rstrip() + "..."
        out["truncated"] = True
    return out


# ---------------------------------------------------------------- filtering

def matches(job, q, role, city, source, since):
    if role and job.get("role") != role:
        return False
    if city and job.get("city") != city:
        return False
    if source and job.get("source") != source:
        return False
    if since is not None:
        posted = job.get("_posted")
        if posted is None or posted < since:
            return False
    if q:
        # Title, company and location only. Searching the description too
        # makes nearly everything match and the results stop feeling relevant.
        return all(word in job["_haystack"] for word in q)
    return True


def counts(jobs, field):
    """{value: n} for a filter dropdown, biggest first."""
    out = {}
    for job in jobs:
        value = job.get(field)
        if value:
            out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


SORTS = {
    "recent": lambda j: (j["_posted"] is None, _desc(j["_posted"])),
    "oldest": lambda j: (j["_posted"] is None, _asc(j["_posted"])),
    "company": lambda j: (job_text(j, "company"), job_text(j, "title")),
    "title": lambda j: (job_text(j, "title"), job_text(j, "company")),
}


def job_text(job, field):
    return (job.get(field) or "").lower()


def _asc(dt):
    return dt.timestamp() if dt else 0.0


def _desc(dt):
    return -dt.timestamp() if dt else 0.0


# ---------------------------------------------------------------- routes

@app.get("/api/health")
def health():
    """Cheap endpoint for a deploy platform's health check.

    Deliberately open even when REQUIRE_AUTH is on: a host's health probe has
    no token, and locking this out would make the service look dead.
    """
    jobs = _load()
    return {
        "status": "ok",
        "jobs": len(jobs),
        "data_loaded_at": _cache["loaded_at"],
        "last_refreshed": _cache["meta"].get("last_refreshed"),
    }


@app.get("/api/auth/config")
def auth_config():
    """What the frontend needs to know before showing a login screen.

    The client id is public by design -- it identifies the app in Google's
    consent screen and is visible in the browser either way. The secret that
    matters is Google's signing key, which only Google has.
    """
    return {"configured": bool(client_id()), "required": auth_required()}


@app.get("/api/me")
def me(user: dict | None = Depends(current_user)):
    """Who the caller is, according to their Google token."""
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


@app.get("/api/meta")
def meta(user: dict | None = Depends(current_user)):
    """Pipeline run metadata: counts per source, dedup layers, tokens, facets."""
    _load()
    return _cache["meta"]


@app.get("/api/jobs")
def list_jobs(
    q: str = Query("", description="free text over title, company and location"),
    role: str = Query("", description="exact role from the taxonomy"),
    city: str = Query("", description="exact canonical city"),
    source: str = Query("", description="greenhouse | lever | ashby | adzuna"),
    posted_within_days: int = Query(0, ge=0, le=365, description="0 means no limit"),
    sort: str = Query("recent", pattern="^(recent|oldest|company|title)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    user: dict | None = Depends(current_user),
):
    """One page of matching jobs, plus the facet counts for the filter menus."""
    jobs = _load()

    # Split the query into words so "intern pune" matches in any order.
    words = [w for w in q.lower().split() if w]

    since = None
    if posted_within_days:
        since = datetime.now(timezone.utc) - timedelta(days=posted_within_days)

    # Text and freshness first. Every facet is then computed from this set with
    # all the other filters applied but NOT its own, so each menu still shows
    # the options you could switch to.
    base = [j for j in jobs if matches(j, words, "", "", "", since)]

    results = [j for j in base if matches(j, [], role, city, source, None)]
    results.sort(key=SORTS[sort])

    start = (page - 1) * page_size
    window = results[start : start + page_size]

    total = len(results)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "total_unfiltered": len(jobs),
        "jobs": [public(j) for j in window],
        "facets": {
            # Each facet ignores its own dimension, so the numbers answer
            # "how many would I get if I picked this?" rather than always
            # matching the current result count -- and a value you have
            # selected never vanishes from its own menu.
            "roles": counts([j for j in base if matches(j, [], "", city, source, None)], "role"),
            "cities": counts([j for j in base if matches(j, [], role, "", source, None)], "city"),
            "sources": counts([j for j in base if matches(j, [], role, city, "", None)], "source"),
        },
        "last_refreshed": _cache["meta"].get("last_refreshed"),
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict | None = Depends(current_user)):
    """One job with its full description."""
    _load()
    job = _cache["by_id"].get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no job with that id")
    return public(job, full_description=True)

"""Greenhouse Job Board API.

Docs: https://docs.greenhouse.io/job-board.html (checked 2026-11-16)
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
  -> {"jobs": [...], "meta": {"total": n}}
  Job fields: id, internal_job_id, title, updated_at, requisition_id,
              location{name}, absolute_url, metadata,
              and with content=true: content (HTML), departments[], offices[]
Public, unauthenticated GET. No stated rate limit; we still back off on 429.
"""

import logging
from datetime import datetime, timezone

from pipeline.config import companies
from pipeline.http import get_json

log = logging.getLogger(__name__)

SOURCE = "greenhouse"
URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def to_raw(job: dict, company_name: str, fetched_at: str) -> dict:
    """Shape one API job into our raw record. Pure, so it is easy to test.

    This keeps the source's own field names under `payload` and lifts only
    what every source has in common. Real normalisation happens in phase 2.
    """
    return {
        "source": SOURCE,
        "source_id": str(job.get("id")),
        "company": company_name,
        "title": job.get("title"),
        "raw_location": (job.get("location") or {}).get("name"),
        "description": job.get("content"),
        "url": job.get("absolute_url"),
        "posted_at": job.get("updated_at"),
        "fetched_at": fetched_at,
        "departments": [d.get("name") for d in (job.get("departments") or [])],
        "offices": [o.get("name") for o in (job.get("offices") or [])],
    }


def fetch() -> list[dict]:
    """Every source module exposes exactly this: fetch() -> list[dict].

    One board failing is logged and skipped; the rest of the run continues.
    """
    boards = companies().get("greenhouse") or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []

    for board in boards:
        token, name = board["token"], board["name"]
        try:
            data = get_json(URL.format(token=token), params={"content": "true"})
        except Exception as e:
            log.warning("  [greenhouse] %s FAILED: %s", token, e)
            continue

        jobs = data.get("jobs") or []
        rows = [to_raw(j, name, fetched_at) for j in jobs]
        out.extend(rows)
        log.info("  [greenhouse] %-12s %4d jobs", token, len(rows))

    return out

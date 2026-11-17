"""Lever Postings API.

Verified live 2026-11-16:
  GET https://api.lever.co/v0/postings/{company}?mode=json
  -> a JSON ARRAY (not an object) of postings.
  Fields: id, text (the title), categories{commitment, department, location,
          allLocations[], team}, country (ISO-2, e.g. "IN"), workplaceType,
          descriptionPlain, description (HTML), hostedUrl, applyUrl,
          createdAt (epoch MILLISECONDS)
Public, unauthenticated.
"""

import logging
from datetime import datetime, timezone

from pipeline.config import companies
from pipeline.http import get_json

log = logging.getLogger(__name__)

SOURCE = "lever"
URL = "https://api.lever.co/v0/postings/{token}"


def to_raw(job: dict, company_name: str, fetched_at: str) -> dict:
    cats = job.get("categories") or {}
    # allLocations is the honest answer when a job is posted in several cities.
    locations = cats.get("allLocations") or ([cats.get("location")] if cats.get("location") else [])
    created = job.get("createdAt")
    return {
        "source": SOURCE,
        "source_id": str(job.get("id")),
        "company": company_name,
        "title": job.get("text"),
        "raw_location": " | ".join(x for x in locations if x) or None,
        "description": job.get("descriptionPlain"),
        "url": job.get("hostedUrl"),
        # createdAt is epoch milliseconds, not seconds and not a string.
        "posted_at": (
            datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
            if isinstance(created, (int, float))
            else None
        ),
        "fetched_at": fetched_at,
        "departments": [cats["department"]] if cats.get("department") else [],
        "offices": [x for x in locations if x],
        # Lever gives a real ISO country code, which beats string-matching
        # "india" against a location like "Noida, Uttar Pradesh".
        "country": job.get("country"),
    }


def fetch() -> list[dict]:
    boards = companies().get("lever") or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []

    for board in boards:
        token, name = board["token"], board["name"]
        try:
            data = get_json(URL.format(token=token), params={"mode": "json"})
        except Exception as e:
            log.warning("  [lever] %s FAILED: %s", token, e)
            continue

        jobs = data if isinstance(data, list) else []
        rows = [to_raw(j, name, fetched_at) for j in jobs]
        out.extend(rows)
        log.info("  [lever] %-12s %4d jobs", token, len(rows))

    return out

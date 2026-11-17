"""Ashby Job Posting API.

Verified live 2026-11-16:
  GET https://api.ashbyhq.com/posting-api/job-board/{name}
  -> {"jobs": [...], "apiVersion": "..."}
  Fields: id, title, department, team, employmentType ("FullTime"/"Intern"),
          location (string), secondaryLocations[], publishedAt (ISO),
          isListed (bool), isRemote, workplaceType,
          address{postalAddress{addressCountry}}, jobUrl, applyUrl,
          descriptionHtml, descriptionPlain
Public, unauthenticated.
"""

import logging
from datetime import datetime, timezone

from pipeline.config import companies
from pipeline.http import get_json

log = logging.getLogger(__name__)

SOURCE = "ashby"
URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def to_raw(job: dict, company_name: str, fetched_at: str) -> dict:
    secondary = [x for x in (job.get("secondaryLocations") or []) if isinstance(x, str)]
    locations = [job.get("location")] + secondary
    country = (
        ((job.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
    )
    return {
        "source": SOURCE,
        "source_id": str(job.get("id")),
        "company": company_name,
        "title": job.get("title"),
        "raw_location": " | ".join(x for x in locations if x) or None,
        "description": job.get("descriptionPlain"),
        "url": job.get("jobUrl"),
        "posted_at": job.get("publishedAt"),
        "fetched_at": fetched_at,
        "departments": [job["department"]] if job.get("department") else [],
        "offices": [x for x in locations if x],
        "country": country,
        # "Intern" here is an explicit signal, better than guessing from a title.
        "employment_type": job.get("employmentType"),
    }


def fetch() -> list[dict]:
    boards = companies().get("ashby") or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []

    for board in boards:
        token, name = board["token"], board["name"]
        try:
            data = get_json(URL.format(token=token))
        except Exception as e:
            log.warning("  [ashby] %s FAILED: %s", token, e)
            continue

        # isListed=False means the posting exists but is not published.
        jobs = [j for j in (data.get("jobs") or []) if j.get("isListed")]
        rows = [to_raw(j, name, fetched_at) for j in jobs]
        out.extend(rows)
        log.info("  [ashby] %-12s %4d jobs", token, len(rows))

    return out

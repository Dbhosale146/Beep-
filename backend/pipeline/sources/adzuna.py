"""Adzuna India search API.

Verified live 2026-11-16 with real keys:
  GET https://api.adzuna.com/v1/api/jobs/in/search/{page}
      ?app_id=..&app_key=..&results_per_page=50&what=intern&max_days_old=30
  -> {"count": n, "results": [...], "mean": x}
  Result fields: id, title, company{display_name},
                 location{display_name, area[]}  <- area is ["India","Karnataka","Bangalore",...]
                 created (ISO), redirect_url, description (TRUNCATED by Adzuna),
                 category{tag,label}, contract_type, contract_time, latitude, longitude

Two things worth knowing:
  1. `description` comes back truncated with a trailing "...", so the fresher
     filter cannot rely on years-of-experience text from Adzuna.
  2. The same job appears under several of our queries, so dedup earns its keep.
"""

import logging
from datetime import datetime, timezone

from pipeline.config import require_env, settings
from pipeline.http import get_json

log = logging.getLogger(__name__)

SOURCE = "adzuna"
URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def to_raw(job: dict, fetched_at: str) -> dict:
    location = job.get("location") or {}
    area = location.get("area") or []
    return {
        "source": SOURCE,
        "source_id": str(job.get("id")),
        "company": (job.get("company") or {}).get("display_name"),
        "title": job.get("title"),
        "raw_location": location.get("display_name"),
        "description": job.get("description"),
        "url": job.get("redirect_url"),
        "posted_at": job.get("created"),
        "fetched_at": fetched_at,
        "departments": [(job.get("category") or {}).get("label")]
        if (job.get("category") or {}).get("label")
        else [],
        # area[0] is the country, the rest narrow down state -> city -> suburb.
        "offices": area,
        "country": area[0] if area else None,
        "employment_type": job.get("contract_time"),
    }


def fetch() -> list[dict]:
    cfg = settings()["adzuna"]
    app_id = require_env("ADZUNA_APP_ID")
    app_key = require_env("ADZUNA_APP_KEY")
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []

    for query in cfg["queries"]:
        got = 0
        for page in range(1, cfg["max_pages"] + 1):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": cfg["results_per_page"],
                "what": query,
                "max_days_old": cfg["max_days_old"],
                "content-type": "application/json",
            }
            url = URL.format(country=cfg["country"], page=page)
            try:
                data = get_json(url, params=params)
            except Exception as e:
                log.warning("  [adzuna] %r page %s FAILED: %s", query, page, e)
                break

            results = data.get("results") or []
            out.extend(to_raw(j, fetched_at) for j in results)
            got += len(results)
            # A short page means we have reached the end of this query.
            if len(results) < cfg["results_per_page"]:
                break

        log.info("  [adzuna] %-16s %4d results", repr(query), got)

    return out

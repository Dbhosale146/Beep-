"""One HTTP helper for every source: timeout, retries, polite User-Agent.

Sources never call requests directly, so retry behaviour is identical
everywhere and there is exactly one place to change it.
"""

import logging
import time

import requests

from pipeline.config import settings

log = logging.getLogger(__name__)


def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list:
    """GET a URL and return parsed JSON. Raises on final failure."""
    cfg = settings()["http"]
    all_headers = {"User-Agent": cfg["user_agent"], "Accept": "application/json"}
    if headers:
        all_headers.update(headers)

    attempts = cfg["retries"] + 1
    wait = cfg["backoff_seconds"]
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(
                url, params=params, headers=all_headers, timeout=cfg["timeout_seconds"]
            )
            # 429 and 5xx are worth retrying; 404 and other 4xx are not.
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from {url}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = e
            if attempt == attempts or _is_permanent(e):
                break
            log.warning("  retry %s/%s for %s after %ss (%s)", attempt, cfg["retries"], url, wait, e)
            time.sleep(wait)
            wait *= 2

    raise last_error


def _is_permanent(e: Exception) -> bool:
    """4xx other than 429 will never succeed, so don't waste retries."""
    r = getattr(e, "response", None)
    return r is not None and 400 <= r.status_code < 500 and r.status_code != 429

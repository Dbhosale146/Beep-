"""Write data/jobs.json and data/run_meta.json.

Both files are what the frontend reads, and run_meta.json is also the evidence
for the writeup: counts per source, what each dedup layer removed, how many
posts were tagged, and the token spend for the run.
"""

import json
import logging

from pipeline.config import data_path

log = logging.getLogger(__name__)

# Fields published to the frontend. Listed explicitly so an internal field
# never leaks into a public file by accident.
PUBLIC_FIELDS = [
    "id",
    "title",
    "company",
    "role",
    "city",
    "raw_location",
    "source",
    "url",
    "posted_at",
    "description",
    "is_fresher",
]


def tokens_since(started_at):
    """Sum the usage_log lines written during this run."""
    path = data_path("usage_log")
    totals = {
        "input": 0,
        "output": 0,
        "thought": 0,
        "cached": 0,
        "calls": 0,
        # Thinking bills at the output rate, so report the billable figure too.
        "billable_output": 0,
    }
    if not path.exists():
        return totals
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("ts", "") < started_at:
                continue
            totals["calls"] += 1
            totals["input"] += record.get("input_tokens", 0)
            totals["output"] += record.get("output_tokens", 0)
            totals["thought"] += record.get("thought_tokens", 0)
            totals["cached"] += record.get("cached_tokens", 0)
    totals["billable_output"] = totals["output"] + totals["thought"]
    return totals


def _sort_key(post):
    # Newest first; posts with no date sort last.
    return (post.get("posted_at") is None, post.get("posted_at") or "")


def write_jobs(posts):
    published = [{k: post.get(k) for k in PUBLIC_FIELDS} for post in posts]
    published.sort(key=_sort_key, reverse=True)
    path = data_path("jobs")
    path.write_text(
        json.dumps(published, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("wrote %s (%d posts)", path, len(published))
    return published


def write_run_meta(meta):
    path = data_path("run_meta")
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote %s", path)
    return meta


def facets(posts):
    """Role and city counts, so the frontend can build filters without scanning."""
    roles = {}
    cities = {}
    for post in posts:
        role = post.get("role") or "Untagged"
        city = post.get("city") or "Untagged"
        roles[role] = roles.get(role, 0) + 1
        cities[city] = cities.get(city, 0) + 1
    return {
        "roles": dict(sorted(roles.items(), key=lambda kv: -kv[1])),
        "cities": dict(sorted(cities.items(), key=lambda kv: -kv[1])),
    }

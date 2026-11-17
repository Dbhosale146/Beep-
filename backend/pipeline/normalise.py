"""Turn raw rows from four different APIs into one schema.

Output schema (one dict per post):
    id, source, source_id, title, company, raw_location, city_guess,
    department, employment_type, description, url, posted_at, fetched_at

city_guess is a cheap alias lookup against config/taxonomy.yaml. It is NOT the
final answer: the LLM still returns `city` in the tagging step. We compute it
here because (a) it tells us whether a post is in India at all, and (b) giving
the model a candidate turns a guess into a confirmation.
"""

import hashlib
import html
import logging
import re

from pipeline.config import settings, taxonomy

log = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(value):
    """Un-escape HTML entities, strip tags, collapse whitespace.

    Greenhouse returns HTML-escaped HTML, so the unescape must happen before
    the tag strip or we leave a visible &lt;p&gt; behind.
    """
    if not value:
        return ""
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return WS_RE.sub(" ", text).strip()


def _city_patterns():
    """Build (canonical_city, regex) pairs, longest name first.

    Longest first so "Navi Mumbai" is tested before "Mumbai" and
    "Greater Noida" before "Noida". Word boundaries stop a short city name
    from matching inside a longer word.
    """
    pairs = []
    for canonical, aliases in (taxonomy()["cities"] or {}).items():
        pairs.append((canonical, canonical))
        for alias in aliases or []:
            pairs.append((canonical, alias))
    pairs.sort(key=lambda p: -len(p[1]))
    return [(c, re.compile(r"\b" + re.escape(name) + r"\b", re.I)) for c, name in pairs]


CITY_PATTERNS = _city_patterns()


def canonical_city(raw_location):
    if not raw_location:
        return None
    for canonical, pattern in CITY_PATTERNS:
        if pattern.search(raw_location):
            return canonical
    return None


def is_india(row, city):
    """Trust an explicit country code when the source gives one.

    Lever returns ISO-2 ("IN"), Ashby returns "India", Adzuna puts the country
    in area[0]. Greenhouse gives nothing, so there we fall back to the location
    string and then to the city match.
    """
    country = (row.get("country") or "").strip().lower()
    if country:
        return country in ("in", "ind", "india")
    if "india" in (row.get("raw_location") or "").lower():
        return True
    return city is not None and city not in ("Remote", "Multiple")


def make_id(source, source_id):
    """Stable short id, so a post keeps the same id across daily runs."""
    return hashlib.sha1(("%s:%s" % (source, source_id)).encode()).hexdigest()[:16]


def normalise_one(row):
    description = clean_text(row.get("description"))
    limit = settings()["export"]["description_chars"]
    raw_location = clean_text(row.get("raw_location")) or None
    departments = row.get("departments") or []
    return {
        "id": make_id(row.get("source", ""), row.get("source_id", "")),
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "title": clean_text(row.get("title")) or None,
        "company": clean_text(row.get("company")) or None,
        "raw_location": raw_location,
        "city_guess": canonical_city(raw_location),
        "department": clean_text(departments[0]) if departments else None,
        "employment_type": row.get("employment_type"),
        "description": description[:limit],
        "url": row.get("url"),
        "posted_at": row.get("posted_at"),
        "fetched_at": row.get("fetched_at"),
    }


def normalise(rows):
    """Returns (india rows in one schema, counts).

    Rows without a title or a url are dropped: we cannot display them and we
    cannot link them, so they are not jobs as far as this tool is concerned.
    """
    counts = {"input": len(rows), "no_title_or_url": 0, "not_india": 0, "kept": 0}
    out = []

    for row in rows:
        clean = normalise_one(row)
        if not clean["title"] or not clean["url"]:
            counts["no_title_or_url"] += 1
            continue
        if not is_india(row, clean["city_guess"]):
            counts["not_india"] += 1
            continue
        out.append(clean)

    counts["kept"] = len(out)
    return out, counts

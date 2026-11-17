"""Keyword rules for "is this a fresher or internship role?".

Runs before the LLM so we do not pay to tag thousands of senior jobs. The LLM
also returns is_fresher, which catches whatever these rules let through.

Every pattern is matched with word boundaries. Without them, "intern" also
matches "Senior Internal Auditor" -- a real false positive from phase 1.
"""

import re

from pipeline.config import load_yaml

RULES = load_yaml("fresher.yaml")


def _compile(words):
    # Longest first so "graduate trainee" is reported rather than "trainee".
    ordered = sorted(words, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in ordered) + r")\b", re.I)


POSITIVE = _compile(RULES["title_positive"])
NEGATIVE = _compile(RULES["title_negative"])
MAX_YEARS = RULES["max_years_experience"]

# Matches "0-1 years", "1 to 3 years", "2+ years", "minimum 3 years".
YEARS_RANGE_RE = re.compile(r"\b(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*year", re.I)
YEARS_MIN_RE = re.compile(r"\b(\d{1,2})\s*\+\s*year", re.I)
YEARS_PLAIN_RE = re.compile(
    r"(?:minimum|min|at least|atleast|over)\s*(?:of\s*)?(\d{1,2})\s*year", re.I
)


def min_years_required(text):
    """Smallest years-of-experience the text seems to ask for, or None.

    A range like "0-1 years" asks for 0. "3+ years" asks for 3. We take the
    lowest number found anywhere, because descriptions often quote a higher
    number for a nice-to-have.
    """
    if not text:
        return None
    found = []
    for a, b in YEARS_RANGE_RE.findall(text):
        found.append(min(int(a), int(b)))
    found += [int(m) for m in YEARS_MIN_RE.findall(text)]
    found += [int(m) for m in YEARS_PLAIN_RE.findall(text)]
    return min(found) if found else None


def looks_fresher(post):
    """(keep?, reason). The reason is counted so the filter can be audited."""
    title = post.get("title") or ""
    description = post.get("description") or ""

    negative = NEGATIVE.search(title)
    if negative:
        return False, "title_negative:" + negative.group(1).lower()

    # An explicit employment type beats any guess made from the title.
    if (post.get("employment_type") or "").lower() in ("intern", "internship"):
        return True, "employment_type:intern"

    positive = POSITIVE.search(title)
    if positive:
        return True, "title_positive:" + positive.group(1).lower()

    years = min_years_required(description)
    if years is not None and years <= MAX_YEARS:
        return True, "years<=%d:%d" % (MAX_YEARS, years)
    if years is not None:
        return False, "years_too_high:%d" % years

    return False, "no_fresher_signal"


def filter_fresher(posts):
    kept = []
    counts = {"input": len(posts), "kept": 0, "dropped": 0}
    reasons = {}

    for post in posts:
        keep, reason = looks_fresher(post)
        reasons[reason] = reasons.get(reason, 0) + 1
        if keep:
            post["fresher_reason"] = reason
            kept.append(post)

    counts["kept"] = len(kept)
    counts["dropped"] = len(posts) - len(kept)
    counts["reasons"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1]))
    return kept, counts

"""Three-layer de-duplication, each layer counted separately.

The layers run cheapest-first and get progressively fuzzier:

  1. exact     same (source, source_id), or the same url
  2. hash      same normalised company + title + city
  3. fuzzy     near-identical titles inside one company (rapidfuzz)

Why three: layer 1 catches one Adzuna job returned by several of our search
queries. Layer 2 catches the same job posted on a company's Greenhouse board
and also indexed by Adzuna, where the ids and urls differ. Layer 3 catches
"SDE Intern" vs "SDE Intern (2027 Batch)" at the same company.

The first row seen always wins, and rows keep their original order, so the
output is stable between runs.
"""

import logging
import re

from rapidfuzz import fuzz

log = logging.getLogger(__name__)

NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# token_sort_ratio catches reordering and typos: "Software Engineer Intern"
# vs "Intern Software Engineer" scores 100.
FUZZY_THRESHOLD = 90

# token_set_ratio catches one title being the other plus a qualifier, which is
# everywhere in Indian fresher postings: "SDE Intern" vs "SDE Intern (2027
# Batch)" scores 100 on set but only 65 on sort. Measured on real titles,
# genuinely different roles score 62-78 here, so 95 separates them cleanly.
SUBSET_THRESHOLD = 95

# ...but a subset match needs a guard, because "Intern" on its own is a subset
# of every intern title. Requiring two tokens in the shorter title stops one
# vague posting from swallowing a company's whole list.
MIN_TOKENS_FOR_SUBSET = 2


def _key(value):
    """Lowercase, drop punctuation, collapse spaces. "Pvt. Ltd" != "Pvt Ltd"."""
    if not value:
        return ""
    return NON_ALNUM_RE.sub(" ", value.lower()).strip()


def layer1_exact(posts):
    """Same source_id from the same source, or the same url."""
    seen_pairs = set()
    seen_urls = set()
    kept = []
    for post in posts:
        pair = (post.get("source"), post.get("source_id"))
        url = (post.get("url") or "").split("?")[0].rstrip("/").lower()
        if pair in seen_pairs or (url and url in seen_urls):
            continue
        seen_pairs.add(pair)
        if url:
            seen_urls.add(url)
        kept.append(post)
    return kept


def layer2_hash(posts):
    """Same normalised company + title + city."""
    seen = set()
    kept = []
    for post in posts:
        key = (
            _key(post.get("company")),
            _key(post.get("title")),
            _key(post.get("city_guess")),
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(post)
    return kept


def titles_match(a, b):
    """Are these two titles the same opening? Assumes the same company.

    Deliberately errs towards merging: showing one posting twice looks worse
    on a job board than collapsing two near-identical ones into one.
    """
    if fuzz.token_sort_ratio(a, b) >= FUZZY_THRESHOLD:
        return True
    shorter = min(a, b, key=len)
    if len(shorter.split()) < MIN_TOKENS_FOR_SUBSET:
        return False
    return fuzz.token_set_ratio(a, b) >= SUBSET_THRESHOLD


def layer3_fuzzy(posts):
    """Near-identical titles within one company.

    Only compared inside the same company, which keeps this cheap and stops
    "Backend Intern" at two different companies being treated as one job.
    """
    kept_titles_by_company = {}
    kept = []
    for post in posts:
        company = _key(post.get("company"))
        title = _key(post.get("title"))
        existing = kept_titles_by_company.setdefault(company, [])
        if any(titles_match(title, other) for other in existing):
            continue
        existing.append(title)
        kept.append(post)
    return kept


def dedup(posts):
    """Returns (unique posts, counts showing what each layer removed)."""
    counts = {"input": len(posts)}

    after1 = layer1_exact(posts)
    counts["removed_layer1_exact"] = len(posts) - len(after1)

    after2 = layer2_hash(after1)
    counts["removed_layer2_hash"] = len(after1) - len(after2)

    after3 = layer3_fuzzy(after2)
    counts["removed_layer3_fuzzy"] = len(after2) - len(after3)

    counts["removed_total"] = len(posts) - len(after3)
    counts["kept"] = len(after3)
    return after3, counts

"""The whole pipeline: fetch -> normalise -> fresher -> dedup -> tag -> export.

Run:
    python -m pipeline.run              # full run
    python -m pipeline.run --no-llm     # everything except tagging (free)
    python -m pipeline.run --limit 50   # tag at most 50 posts, for a cheap test

Failure rules:
  * One source failing is logged and skipped; the run continues.
  * If the run fails before the export step, nothing is written, so the
    previous data/jobs.json stays in place and the site keeps working.
  * A post that has disappeared from its source feed simply is not in this
    run's output, which is how stale posts drop off.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from pipeline import export
from pipeline.config import data_path, load_env
from pipeline.dedup import dedup
from pipeline.fresher import filter_fresher
from pipeline.normalise import normalise
from pipeline.run_fetch import fetch_all

log = logging.getLogger("run")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="skip tagging")
    parser.add_argument("--limit", type=int, default=0, help="cap posts sent to the LLM")
    parser.add_argument("--raw", default="", help="reuse a raw_jobs.json instead of fetching")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    # The Gemini SDK logs one INFO line per HTTP request, which buries our own
    # progress output behind 59 copies of "POST .../interactions 200 OK".
    # Note httpx2/httpcore2: google-genai vendors its own copies of httpx and
    # httpcore under those names, so silencing plain "httpx" does nothing.
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_env()
    started = datetime.now(timezone.utc)
    started_iso = started.isoformat()

    # ---- fetch -------------------------------------------------------------
    if args.raw:
        log.info("reusing raw file %s", args.raw)
        raw = json.loads(open(args.raw, encoding="utf-8").read())
        source_counts = {}
        for row in raw:
            key = row.get("source", "?")
            source_counts[key] = source_counts.get(key, 0) + 1
    else:
        raw, source_counts = fetch_all()
        # Keep the raw fetch so a re-run can skip ~3 minutes of network with
        # --raw. Gitignored; it is a debugging artefact, not output.
        with open(data_path("raw"), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

    # ---- normalise ---------------------------------------------------------
    log.info("")
    log.info("normalising %d raw rows ...", len(raw))
    posts, normalise_counts = normalise(raw)
    log.info(
        "  kept %d india posts (dropped %d non-india, %d missing title/url)",
        normalise_counts["kept"],
        normalise_counts["not_india"],
        normalise_counts["no_title_or_url"],
    )

    # ---- fresher filter ----------------------------------------------------
    posts, fresher_counts = filter_fresher(posts)
    log.info("fresher filter: kept %d, dropped %d", fresher_counts["kept"], fresher_counts["dropped"])
    for reason, n in list(fresher_counts["reasons"].items())[:8]:
        log.info("    %-28s %d", reason, n)

    # ---- dedup -------------------------------------------------------------
    posts, dedup_counts = dedup(posts)
    log.info(
        "dedup: layer1 exact -%d, layer2 hash -%d, layer3 fuzzy -%d -> %d unique",
        dedup_counts["removed_layer1_exact"],
        dedup_counts["removed_layer2_hash"],
        dedup_counts["removed_layer3_fuzzy"],
        dedup_counts["kept"],
    )

    # ---- tag ---------------------------------------------------------------
    if args.no_llm:
        log.info("--no-llm: skipping tagging")
        for post in posts:
            post.setdefault("role", "Untagged")
            post.setdefault("city", post.get("city_guess") or "Untagged")
            post.setdefault("is_fresher", True)
        tag_counts = {"skipped": True}
    else:
        from pipeline.tag import tag_all

        to_tag = posts[: args.limit] if args.limit else posts
        if args.limit:
            log.info("--limit %d: tagging only the first %d posts", args.limit, len(to_tag))
            for post in posts[args.limit :]:
                post["role"] = "Untagged"
                post["city"] = post.get("city_guess") or "Untagged"
                post["is_fresher"] = True
        _, tag_counts = tag_all(to_tag)
        log.info(
            "tagged %d (%d from cache, %d via %d LLM calls, %d untagged)",
            tag_counts["tagged"],
            tag_counts["from_cache"],
            tag_counts["sent_to_llm"],
            tag_counts["llm_calls"],
            tag_counts["untagged"],
        )

    # ---- drop LLM-identified non-freshers ---------------------------------
    before = len(posts)
    posts = [p for p in posts if p.get("is_fresher") is not False]
    llm_dropped = before - len(posts)
    if llm_dropped:
        log.info("dropped %d posts the LLM judged not fresher", llm_dropped)

    # ---- export ------------------------------------------------------------
    published = export.write_jobs(posts)
    tokens = export.tokens_since(started_iso)
    finished = datetime.now(timezone.utc)

    meta = {
        "last_refreshed": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "total_jobs": len(published),
        "counts_per_source_raw": source_counts,
        "counts_per_source_published": _by_source(published),
        "normalise": normalise_counts,
        "fresher_filter": fresher_counts,
        "dedup": dedup_counts,
        "llm_dropped_not_fresher": llm_dropped,
        "tagging": tag_counts,
        "tokens": tokens,
        "facets": export.facets(published),
    }
    export.write_run_meta(meta)

    log.info("")
    log.info("=== run complete in %.1fs ===", meta["duration_seconds"])
    log.info("published %d jobs", meta["total_jobs"])
    log.info("tokens: in=%s billable_out=%s over %s calls",
             tokens["input"], tokens["billable_output"], tokens["calls"])
    return 0 if published else 1


def _by_source(posts):
    out = {}
    for post in posts:
        key = post.get("source") or "?"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    raise SystemExit(main())

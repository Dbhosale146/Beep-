"""Phase 1 entry point: fetch every source to data/raw_jobs.json.

Run: python -m pipeline.run_fetch
"""

import json
import logging
import sys
from datetime import datetime, timezone

from pipeline.config import data_path
from pipeline.sources import SOURCES

log = logging.getLogger("fetch")


def fetch_all() -> tuple[list[dict], dict]:
    """Returns (all raw records, per-source counts).

    Failure rule: a source that raises is logged and skipped with count -1,
    so one broken API can never stop the run.
    """
    rows: list[dict] = []
    counts: dict[str, int] = {}

    for name, module in SOURCES.items():
        log.info("fetching %s ...", name)
        try:
            got = module.fetch()
        except Exception as e:
            log.error("source %s FAILED entirely: %s", name, e)
            counts[name] = -1
            continue
        counts[name] = len(got)
        rows.extend(got)

    return rows, counts


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(message)s", stream=sys.stderr
    )
    started = datetime.now(timezone.utc)

    rows, counts = fetch_all()

    out = data_path("raw")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    log.info("")
    log.info("=== fetch summary ===")
    for name, n in counts.items():
        log.info("%-12s %s", name, "FAILED" if n < 0 else n)
    india = sum(1 for r in rows if "india" in (r.get("raw_location") or "").lower())
    log.info("%-12s %d", "TOTAL", len(rows))
    log.info("%-12s %d  (raw_location mentions India)", "of which IN", india)
    log.info("wrote %s in %.1fs", out, (datetime.now(timezone.utc) - started).total_seconds())

    # Non-zero exit only if every source failed, so CI can tell real breakage
    # from a single flaky board.
    return 0 if any(n > 0 for n in counts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

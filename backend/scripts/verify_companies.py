"""Check every token in config/companies.yaml still returns jobs.

Run before a demo: boards get renamed and go empty without warning.
    python scripts/verify_companies.py
Exits 1 if any token is dead, so it can be a CI step later.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import companies  # noqa: E402
from pipeline.http import get_json  # noqa: E402
from pipeline.sources.greenhouse import URL as GH_URL  # noqa: E402


def check_greenhouse(token: str) -> tuple[int, int]:
    data = get_json(GH_URL.format(token=token), params={"content": "false"})
    jobs = data.get("jobs") or []
    india = [j for j in jobs if "india" in ((j.get("location") or {}).get("name") or "").lower()]
    return len(jobs), len(india)


def main() -> int:
    dead = []
    boards = companies().get("greenhouse") or []
    print(f"checking {len(boards)} greenhouse tokens\n")

    for board in boards:
        token = board["token"]
        try:
            total, india = check_greenhouse(token)
        except Exception as e:
            print(f"  {token:14} DEAD        ({e})")
            dead.append(token)
            continue
        flag = "" if india else "   <- no India jobs today"
        print(f"  {token:14} {total:5} jobs  india={india}{flag}")
        if total == 0:
            dead.append(token)

    print()
    if dead:
        print(f"{len(dead)} token(s) returned nothing: {', '.join(dead)}")
        return 1
    print("all tokens healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

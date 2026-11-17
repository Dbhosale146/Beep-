"""Write a random sample of posts to a CSV for hand-labelling.

    python scripts/sample_for_eval.py                 # 50 posts, stratified
    python scripts/sample_for_eval.py --n 100 --seed 7

The model's answers go in model_* columns and your answers go in the empty
true_* columns next to them, so you can fill the CSV in a spreadsheet and the
two sets never get mixed up. Then:

    python scripts/score_eval.py data/eval_sample.csv

The sample is stratified by source: without it, Adzuna supplies ~98% of posts
and the sample says nothing about how tagging does on the company boards.
A fixed --seed makes the sample reproducible, which matters if someone asks
how the number was produced.
"""

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import ROOT, data_path  # noqa: E402

COLUMNS = [
    # what the post is
    "id",
    "source",
    "title",
    "company",
    "raw_location",
    "url",
    # what the model said
    "model_role",
    "model_city",
    "model_is_fresher",
    # what I say -- left blank on purpose
    "true_role",
    "true_city",
    "true_is_fresher",
    "notes",
]


def stratified_sample(posts, n, seed):
    """Take n posts spread across sources in proportion to their size.

    Every source present gets at least one row, so a small source is still
    represented. Remaining slots are handed out largest-source-first.
    """
    rng = random.Random(seed)
    by_source = defaultdict(list)
    for post in posts:
        by_source[post.get("source") or "?"].append(post)
    for rows in by_source.values():
        rng.shuffle(rows)

    sources = sorted(by_source, key=lambda s: -len(by_source[s]))
    total = len(posts)
    quota = {}
    for source in sources:
        share = len(by_source[source]) / total
        quota[source] = max(1, round(share * n))

    # round() can overshoot or undershoot n; fix it up on the biggest sources.
    while sum(quota.values()) > n:
        for source in reversed(sources):
            if quota[source] > 1 and sum(quota.values()) > n:
                quota[source] -= 1
    while sum(quota.values()) < n:
        for source in sources:
            if quota[source] < len(by_source[source]) and sum(quota.values()) < n:
                quota[source] += 1

    out = []
    for source in sources:
        out.extend(by_source[source][: quota[source]])
    rng.shuffle(out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/eval_sample.csv")
    args = parser.parse_args()

    posts = json.loads(data_path("jobs").read_text(encoding="utf-8"))
    if not posts:
        print("data/jobs.json is empty - run the pipeline first")
        return 1

    sample = stratified_sample(posts, min(args.n, len(posts)), args.seed)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for post in sample:
            writer.writerow(
                {
                    "id": post["id"],
                    "source": post["source"],
                    "title": post["title"],
                    "company": post["company"],
                    "raw_location": post["raw_location"],
                    "url": post["url"],
                    "model_role": post["role"],
                    "model_city": post["city"],
                    "model_is_fresher": post["is_fresher"],
                    "true_role": "",
                    "true_city": "",
                    "true_is_fresher": "",
                    "notes": "",
                }
            )

    counts = {}
    for post in sample:
        counts[post["source"]] = counts.get(post["source"], 0) + 1
    print(f"wrote {out_path} with {len(sample)} posts")
    print("per source:", counts)
    print("\nFill in true_role / true_city / true_is_fresher, then run:")
    print(f"  python scripts/score_eval.py {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

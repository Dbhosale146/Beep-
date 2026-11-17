"""Score a hand-labelled eval CSV: role accuracy, city accuracy, fresher accuracy.

    python scripts/score_eval.py data/eval_sample.csv

Only rows where you filled in a true_* value are scored for that field, so you
can label role first and city later. Rows left entirely blank are reported as
unlabelled rather than silently counted as correct.
"""

import argparse
import csv
import sys
from collections import Counter


def norm(value):
    return (value or "").strip()


def as_bool(value):
    v = norm(value).lower()
    if v in ("true", "yes", "y", "1"):
        return True
    if v in ("false", "no", "n", "0"):
        return False
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("empty CSV")
        return 1

    scores = {"role": [0, 0], "city": [0, 0], "is_fresher": [0, 0]}  # [correct, labelled]
    mistakes = {"role": Counter(), "city": Counter()}
    unlabelled = 0

    for row in rows:
        labelled_any = False

        for field in ("role", "city"):
            truth = norm(row.get("true_" + field))
            if not truth:
                continue
            labelled_any = True
            predicted = norm(row.get("model_" + field))
            scores[field][1] += 1
            if predicted.lower() == truth.lower():
                scores[field][0] += 1
            else:
                mistakes[field][f"{predicted} -> {truth}"] += 1

        truth_fresher = as_bool(row.get("true_is_fresher"))
        if truth_fresher is not None:
            labelled_any = True
            scores["is_fresher"][1] += 1
            if as_bool(row.get("model_is_fresher")) is truth_fresher:
                scores["is_fresher"][0] += 1

        if not labelled_any:
            unlabelled += 1

    print(f"rows in file: {len(rows)}   unlabelled: {unlabelled}\n")
    for field, (correct, labelled) in scores.items():
        if not labelled:
            print(f"{field:12} no labels yet")
            continue
        print(f"{field:12} {correct}/{labelled} = {100 * correct / labelled:.1f}%")

    for field in ("role", "city"):
        if mistakes[field]:
            print(f"\n{field} mistakes (model -> truth):")
            for pair, n in mistakes[field].most_common(10):
                print(f"  {n:3}  {pair}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

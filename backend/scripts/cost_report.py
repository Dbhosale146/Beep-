"""Cost report from data/usage_log.jsonl.

Prices are arguments, not constants, so the figure in the writeup is always
computed from prices quoted at the time rather than from a number that has
silently gone stale in a config file.

    python scripts/cost_report.py --input-price 0.30 --output-price 2.50

Prices are USD per 1,000,000 tokens.

Note on thinking tokens: Gemini reports total_thought_tokens separately from
total_output_tokens, and thinking bills at the output rate. This script bills
output + thought. Counting only output would understate the real cost.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import data_path  # noqa: E402


def load_records(path, since):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since and record.get("ts", "") < since:
                continue
            records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-price", type=float, required=True,
                        help="USD per 1M input tokens")
    parser.add_argument("--output-price", type=float, required=True,
                        help="USD per 1M output tokens (also billed for thinking)")
    parser.add_argument("--since", default="",
                        help="only count calls with ts >= this ISO timestamp")
    args = parser.parse_args()

    path = data_path("usage_log")
    if not path.exists():
        print(f"no usage log at {path} - run the pipeline first")
        return 1

    records = load_records(path, args.since)
    if not records:
        print("no usage records matched")
        return 1

    calls = len(records)
    posts = sum(r.get("posts_in_call", 0) for r in records)
    tokens_in = sum(r.get("input_tokens", 0) for r in records)
    tokens_out = sum(r.get("output_tokens", 0) for r in records)
    tokens_thought = sum(r.get("thought_tokens", 0) for r in records)
    tokens_cached = sum(r.get("cached_tokens", 0) for r in records)
    billable_out = tokens_out + tokens_thought

    cost_in = tokens_in / 1_000_000 * args.input_price
    cost_out = billable_out / 1_000_000 * args.output_price
    total = cost_in + cost_out

    models = Counter(r.get("model") for r in records)
    prompts = Counter(r.get("prompt_version") for r in records)
    retries = sum(1 for r in records if r.get("attempt", 1) > 1)

    print("=" * 56)
    print("LLM cost report")
    print("=" * 56)
    print(f"model(s)              {', '.join(f'{m} x{n}' for m, n in models.items())}")
    print(f"prompt version(s)     {', '.join(f'{p} x{n}' for p, n in prompts.items())}")
    print(f"LLM calls             {calls}  ({retries} were retries)")
    print(f"posts tagged          {posts}")
    print()
    print(f"input tokens          {tokens_in:>12,}")
    print(f"output tokens         {tokens_out:>12,}")
    print(f"thinking tokens       {tokens_thought:>12,}   (billed at output rate)")
    print(f"cached input tokens   {tokens_cached:>12,}")
    print(f"billable output       {billable_out:>12,}")
    print()
    if posts:
        print(f"tokens per post       in {tokens_in / posts:.1f}   out {billable_out / posts:.1f}")
    print(f"prices used           ${args.input_price}/1M in, ${args.output_price}/1M out")
    print()
    print(f"cost, input           ${cost_in:.4f}")
    print(f"cost, output          ${cost_out:.4f}")
    print(f"cost, total           ${total:.4f}")
    if posts:
        print()
        print(f"COST PER 1,000 POSTS  ${total / posts * 1000:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

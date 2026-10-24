"""CLI: python -m whyitmatters.eval --seeds 20 [--check] [--json report.json]

Seeds start at 1000 so evaluation never reuses the seeds used to tune thresholds (0-39).
"""

from __future__ import annotations

import argparse
import json
import sys

from whyitmatters.eval import score_match, summarize
from whyitmatters.simulator import simulate

TARGETS = {"precision": 0.60, "recall": 0.75, "timeline_accuracy": 0.75}
EVAL_SEED_OFFSET = 1000


def main() -> None:
    ap = argparse.ArgumentParser(description="Detection quality vs ground truth")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--check", action="store_true", help="Exit non-zero if below targets")
    ap.add_argument("--json", default=None, help="Write the summary as JSON")
    args = ap.parse_args()

    scores = [score_match(simulate(EVAL_SEED_OFFSET + i)) for i in range(args.seeds)]
    summary = summarize(scores).as_dict()
    for s in scores:
        print(f"  {s.match_id:<22} shifts {s.true_shifts}  detected {s.detected}  hits {s.hits}"
              f"  live acc {s.minute_accuracy:.0%}  timeline acc {s.timeline_accuracy:.0%}")
    print(json.dumps(summary, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    if args.check:
        failed = [k for k, v in TARGETS.items() if summary[k] < v]
        if failed:
            print(f"Below target: {', '.join(failed)}", file=sys.stderr)
            sys.exit(1)
        print("All detection targets met.")


if __name__ == "__main__":
    main()

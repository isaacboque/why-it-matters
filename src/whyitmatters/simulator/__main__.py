"""CLI: python -m whyitmatters.simulator --seed 7 --out match.jsonl"""

from __future__ import annotations

import argparse
from collections import Counter

from whyitmatters.schema import EventType, Outcome
from whyitmatters.simulator import simulate, write_match


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a synthetic match")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None, help="Write the match as JSONL")
    args = ap.parse_args()

    m = simulate(args.seed)
    types = Counter(e.type for e in m.events)
    passes = [e for e in m.events if e.type == EventType.PASS]
    done = sum(e.outcome == Outcome.COMPLETE for e in passes)
    home, away = m.meta.home, m.meta.away
    last = m.events[-1]
    print(f"{m.meta.match_id}: {home.name} {last.score_home}-{last.score_away} {away.name}")
    print(f"events {len(m.events)} | passes {len(passes)} ({done / len(passes):.0%} complete) "
          f"| shots {types[EventType.SHOT]}")
    for p in m.truth.phases:
        print(f"  {p.start_minute:5.1f}-{p.end_minute:5.1f}  {p.kind}")
    if args.out:
        write_match(m, args.out)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

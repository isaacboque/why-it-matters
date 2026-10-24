"""CLI: python -m whyitmatters.agents --seed 7 --mode fan --lang ca [--club home] [--faults 0.3]"""

from __future__ import annotations

import argparse
import json
import time

from whyitmatters.agents import Viewer, run_match
from whyitmatters.simulator import simulate


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the agent team over a synthetic match")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mode", choices=["analyst", "fan", "player_focus"], default="analyst")
    ap.add_argument("--lang", choices=["en", "es", "ca"], default="en")
    ap.add_argument("--club", choices=["home", "away"], default=None)
    ap.add_argument("--player", default=None, help="player id, e.g. nba-9")
    ap.add_argument("--faults", type=float, default=0.0,
                    help="share of first drafts the Explainer mis-states (demo of the Verifier)")
    args = ap.parse_args()

    match = simulate(args.seed)
    started = time.perf_counter()
    orch = run_match(match, fault_rate=args.faults, seed=args.seed)
    elapsed = time.perf_counter() - started
    viewer = Viewer(mode=args.mode, lang=args.lang, club=args.club, player_id=args.player)

    print(f"{match.meta.home.name} vs {match.meta.away.name}  ({args.mode}, {args.lang})\n")
    for pc in orch.personalize(viewer):
        star = "*" if pc.for_you else " "
        print(f"{star}{pc.minute:>3}'  {pc.headline}")
        print(f"        {pc.body}")
    recap = orch.recap_for(viewer)
    print(f"\n{recap.headline}\n{recap.summary}")
    for m in recap.moments:
        print(f"  {m.minute:>3}'  {m.headline}")
    print("\nTrust:", json.dumps(orch.stats.as_dict()))
    print(f"Insights {len(orch.insights)} | cues aired {len(orch.cues)} | "
          f"held {len(orch.producer.held)} | whole match in {elapsed:.2f}s")


if __name__ == "__main__":
    main()

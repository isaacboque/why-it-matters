"""CLI: python -m whyitmatters.agents --seed 7 --mode fan --lang ca [--club home] [--faults 0.3]

The text writer follows WIM_GENERATOR (template by default; llm needs credentials, see
docs/LLM.md), and --lang takes any BCP-47 code.
"""

from __future__ import annotations

import argparse
import json
import time

from whyitmatters.agents import Viewer, run_match
from whyitmatters.agents.llm import choose_generator
from whyitmatters.agents.models import METRIC_TAGS
from whyitmatters.simulator import simulate


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the agent team over a synthetic match")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--mode", choices=["analyst", "fan", "player_focus", "coach"], default="analyst"
    )
    ap.add_argument(
        "--metric",
        choices=list(METRIC_TAGS),
        default=None,
        help="follow one thread only (goals always show)",
    )
    ap.add_argument("--lang", default="en", help="BCP-47 code; en/es/ca offline, others via llm")
    ap.add_argument("--club", choices=["home", "away"], default=None)
    ap.add_argument("--player", default=None, help="player id, e.g. nba-9")
    ap.add_argument(
        "--faults",
        type=float,
        default=0.0,
        help="share of first drafts the Explainer mis-states (demo of the Verifier)",
    )
    args = ap.parse_args()

    make_generator, status = choose_generator()
    match = simulate(args.seed)
    started = time.perf_counter()
    orch = run_match(match, fault_rate=args.faults, seed=args.seed, generator=make_generator())
    elapsed = time.perf_counter() - started
    viewer = Viewer(
        mode=args.mode, lang=args.lang, club=args.club, player_id=args.player, metric=args.metric
    )

    print(f"{match.meta.home.name} vs {match.meta.away.name}  ({args.mode}, {args.lang})")
    print(f"writer: {status}\n")
    for pc in orch.personalize(viewer):
        star = "*" if pc.for_you else " "
        by = {"model": " [model]", "template_fallback": " [template fallback]"}.get(
            pc.written_by, ""
        )
        note = " [translation unavailable: English]" if pc.translation_unavailable else ""
        print(f"{star}{pc.minute:>3}'  {pc.headline}{by}{note}")
        print(f"        {pc.body}")
    recap = orch.recap_for(viewer)
    print(f"\n{recap.headline}\n{recap.summary}")
    for m in recap.moments:
        print(f"  {m.minute:>3}'  {m.headline}")
    print("\nTrust:", json.dumps({**orch.stats.as_dict(), **_writers(orch)}))
    print(
        f"Insights {len(orch.insights)} | cues aired {len(orch.cues)} | "
        f"held {len(orch.producer.held)} | whole match in {elapsed:.2f}s"
    )


def _writers(orch) -> dict[str, float]:
    t = orch.trust()
    return {k: t[k] for k in ("written_by_model", "written_by_fallback", "written_by_template")}


if __name__ == "__main__":
    main()

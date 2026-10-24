"""CLI: replay a match file through the Match Pulse engine.

python -m whyitmatters.pulse match.jsonl
"""

from __future__ import annotations

import argparse

from whyitmatters.pulse import run_pulse
from whyitmatters.simulator import read_match

LABEL = {"home_control": "{home} in control", "away_control": "{away} in control",
         "chaos": "chaos", "balanced": "balanced"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay a match through the Match Pulse engine")
    ap.add_argument("path")
    args = ap.parse_args()

    m = read_match(args.path)
    names = {"home": m.meta.home.short_name, "away": m.meta.away.short_name}
    pulse = run_pulse(m.events, m.meta)

    def label(s: str) -> str:
        return LABEL[s].format(**names)

    print(f"{m.meta.home.name} vs {m.meta.away.name}")
    for t in pulse.transitions:
        a = t.after
        print(f"  {t.detected_minute:>3}'  {label(t.from_state):>18} -> {label(t.to_state):<18}"
              f" poss {a.home.possession_share:.0%}/{a.away.possession_share:.0%}"
              f"  tilt {a.home.field_tilt:.0%}/{a.away.field_tilt:.0%}"
              f"  turnovers/min {a.turnovers_per_min}")
    print("Ground truth:")
    for p in m.truth.phases:
        print(f"  {p.start_minute:5.1f}-{p.end_minute:5.1f}  {label(p.kind)}")


if __name__ == "__main__":
    main()

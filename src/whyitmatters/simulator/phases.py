"""Scripted tactical phases: the hidden ground truth that drives team behaviour.

Each phase sets how both teams play for a stretch of the match. The detector never sees
this script; evaluation compares what the Match Pulse engine infers against it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from whyitmatters.schema import Phase, PhaseKind, Side


@dataclass(frozen=True)
class Style:
    skill: float  # base pass completion before difficulty and pressure
    press: float  # 0..1, how often and how high the team presses without the ball
    tempo: float  # multiplier on seconds per action (lower = faster)
    directness: float  # multiplier on forward progression per pass

    def blend(self, other: Style, w: float) -> Style:
        """Linear mix: w=0 -> self, w=1 -> other."""
        return Style(
            skill=self.skill + (other.skill - self.skill) * w,
            press=self.press + (other.press - self.press) * w,
            tempo=self.tempo + (other.tempo - self.tempo) * w,
            directness=self.directness + (other.directness - self.directness) * w,
        )


DOMINANT = Style(skill=0.92, press=0.70, tempo=0.90, directness=0.70)
DOMINATED = Style(skill=0.68, press=0.10, tempo=0.95, directness=1.70)
BALANCED = Style(skill=0.85, press=0.35, tempo=1.00, directness=1.00)
CHAOTIC = Style(skill=0.62, press=0.80, tempo=0.60, directness=2.00)

STYLES: dict[PhaseKind, dict[Side, Style]] = {
    "balanced": {"home": BALANCED, "away": BALANCED},
    "home_control": {"home": DOMINANT, "away": DOMINATED},
    "away_control": {"home": DOMINATED, "away": DOMINANT},
    "chaos": {"home": CHAOTIC, "away": CHAOTIC},
}

BLEND_MINUTES = 1.5
MATCH_MINUTES = 90.0


def script_phases(rng: random.Random) -> list[Phase]:
    """A plausible run of phases covering 0..90 minutes."""
    phases: list[Phase] = []
    start = 0.0
    kind: PhaseKind = "balanced"
    end = round(start + rng.uniform(8, 14), 2)
    phases.append(Phase(kind=kind, start_minute=start, end_minute=end))
    options: list[PhaseKind] = ["home_control", "away_control", "chaos", "balanced"]
    while end < MATCH_MINUTES:
        start = end
        kind = rng.choice([k for k in options if k != kind])
        length = rng.uniform(9, 20) if kind != "chaos" else rng.uniform(6, 11)
        end = round(min(MATCH_MINUTES, start + length), 2)
        if MATCH_MINUTES - end < 6:  # avoid a sliver of a phase at the end
            end = MATCH_MINUTES
        phases.append(Phase(kind=kind, start_minute=start, end_minute=end))
    return phases


def phase_at(phases: list[Phase], minute: float) -> Phase:
    for p in phases:
        if p.start_minute <= minute < p.end_minute:
            return p
    return phases[-1]


def style_at(phases: list[Phase], minute: float, side: Side, quality: float) -> Style:
    """Team style at a match minute, blended across phase boundaries.

    `quality` is a small per-team offset so the same phase never plays out identically.
    """
    current = phase_at(phases, minute)
    style = STYLES[current.kind][side]
    idx = phases.index(current)
    since_start = minute - current.start_minute
    if idx > 0 and since_start < BLEND_MINUTES:
        prev = STYLES[phases[idx - 1].kind][side]
        style = prev.blend(style, since_start / BLEND_MINUTES)
    return Style(
        skill=min(0.97, style.skill + quality),
        press=style.press,
        tempo=style.tempo,
        directness=style.directness,
    )

"""Score shape detection (formation in and out of possession, block type) against the
simulator's scripted shapes. Windows of 5 minutes that sit fully inside one scripted phase,
starting at least 1 minute after it begins (the team needs time to get into shape)."""

from __future__ import annotations

from dataclasses import dataclass

from whyitmatters.pulse.metrics import MinuteCounter
from whyitmatters.pulse.shape import block_of
from whyitmatters.schema import Match

WINDOW = 5


@dataclass
class ShapeScore:
    windows: int = 0
    formation_out: int = 0
    formation_in: int = 0
    block: int = 0

    def add(self, other: ShapeScore) -> None:
        self.windows += other.windows
        self.formation_out += other.formation_out
        self.formation_in += other.formation_in
        self.block += other.block

    def as_dict(self) -> dict[str, float]:
        n = self.windows or 1
        return {
            "shape_windows": self.windows,
            "formation_out_accuracy": round(self.formation_out / n, 3),
            "formation_in_accuracy": round(self.formation_in / n, 3),
            "block_accuracy": round(self.block / n, 3),
        }


def score_shapes(match: Match) -> ShapeScore:
    counter = MinuteCounter()
    for ev in match.events:
        counter.ingest(ev)
    score = ShapeScore()
    last = match.events[-1].minute
    for end in range(WINDOW, min(90, last)):
        start = end - WINDOW + 1
        for truth in match.truth.shapes:
            if not (truth.start_minute + 1 <= start and end + 1 <= truth.end_minute):
                continue
            team = getattr(counter.window(end, WINDOW), truth.side)
            if team.shape_out is None or team.shape_in is None:
                continue
            score.windows += 1
            score.formation_out += team.shape_out.formation == truth.out_of_possession
            score.formation_in += team.shape_in.formation == truth.in_possession
            score.block += block_of(team.shape_out.line_height) == truth.block
    return score

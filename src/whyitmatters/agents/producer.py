"""Producer: the editor in the gallery. Applies an on-air budget and times the cues.

At most `budget` cues per rolling `window_min` match minutes. Goals always air (they
take a slot but never wait); everything else must beat the budget on significance.
"""

from __future__ import annotations

from whyitmatters.agents.models import Cue, Insight

ON_SCREEN_SECONDS = {"goal": 25.0, "state_shift": 15.0, "big_chance": 12.0,
                     "top_speed": 10.0, "pass_master": 10.0}
MIN_SIGNIFICANCE = 0.3


class Producer:
    name = "producer"

    def __init__(self, budget: int = 3, window_min: float = 5.0):
        self.budget = budget
        self.window_s = window_min * 60.0
        self.aired: list[Cue] = []
        self.held: list[Insight] = []

    def _recent(self, t: float) -> list[Cue]:
        return [c for c in self.aired if t - c.t_in < self.window_s]

    def run(self, insight: Insight) -> Cue | None:
        recent = self._recent(insight.t)
        if insight.kind != "goal":
            if insight.significance < MIN_SIGNIFICANCE or len(recent) >= self.budget:
                self.held.append(insight)
                return None
        priority = 1 if insight.kind == "goal" else 2 if insight.significance >= 0.6 else 3
        # goals cut in immediately; anything else waits for the screen to clear
        t_in = insight.t if insight.kind == "goal" else max(
            insight.t, self.aired[-1].t_out if self.aired else 0.0
        )
        if insight.kind != "goal" and t_in - insight.t > 90:
            self.held.append(insight)  # stale by the time a slot frees up
            return None
        cue = Cue(
            cue_id=f"cue-{len(self.aired) + 1:03d}", insight_id=insight.id, kind=insight.kind,
            t_in=round(t_in, 1), t_out=round(t_in + ON_SCREEN_SECONDS[insight.kind], 1),
            minute=insight.minute, priority=priority, headline=insight.headline,
            body=insight.body, side=insight.side, player_id=insight.player_id,
            evidence_event_ids=insight.evidence, claims=insight.claims, slots=insight.slots,
        )
        self.aired.append(cue)
        return cue

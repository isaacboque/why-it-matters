"""Producer: the editor in the gallery. Applies an on-air budget and times the cues.

At most `budget` cues per rolling `window_min` match minutes. Goals always air (they
take a slot but never wait); everything else must beat the budget on significance.
"""

from __future__ import annotations

from whyitmatters.agents.models import Cue, Insight

ON_SCREEN_SECONDS = {
    "goal": 25.0,
    "state_shift": 15.0,
    "big_chance": 12.0,
    "top_speed": 10.0,
    "pass_master": 10.0,
    "press_surge": 15.0,
    "midfield_battle": 15.0,
    "danger_turnovers": 15.0,
    "direct_switch": 15.0,
    "pass_difficulty": 10.0,
    "shot_speed": 10.0,
    "line_breakers": 15.0,
    "zone_damage": 15.0,
    "momentum_swing": 15.0,
    "shape_change": 15.0,
    "lines_stretched": 15.0,
    "most_dangerous_pass": 12.0,
}
MIN_SIGNIFICANCE = 0.3
MAX_DELAY_S = 90.0  # an insight that cannot air within this long of happening is stale


class Producer:
    name = "producer"

    def __init__(self, budget: int = 3, window_min: float = 5.0):
        self.budget = budget
        self.window_s = window_min * 60.0
        self.aired: list[Cue] = []
        self.held: list[Insight] = []

    def _fits(self, t_in: float) -> bool:
        """Would a cue at `t_in` keep every `window_s` window that contains it within budget?"""
        times = sorted([c.t_in for c in self.aired] + [t_in])
        for start in times:
            if start <= t_in < start + self.window_s:
                if sum(start <= t < start + self.window_s for t in times) > self.budget:
                    return False
        return True

    def run(self, insight: Insight) -> Cue | None:
        if insight.kind == "goal":
            t_in = insight.t  # goals cut in immediately and always air
        else:
            # everything else waits for the screen to clear, and must fit the budget at the
            # moment it would actually appear
            t_in = max(insight.t, max((c.t_out for c in self.aired), default=0.0))
            if (
                insight.significance < MIN_SIGNIFICANCE
                or t_in - insight.t > MAX_DELAY_S
                or not self._fits(t_in)
            ):
                self.held.append(insight)
                return None
        priority = 1 if insight.kind == "goal" else 2 if insight.significance >= 0.6 else 3
        cue = Cue(
            cue_id=f"cue-{len(self.aired) + 1:03d}",
            insight_id=insight.id,
            kind=insight.kind,
            t_in=round(t_in, 1),
            t_out=round(t_in + ON_SCREEN_SECONDS[insight.kind], 1),
            minute=insight.minute,
            priority=priority,
            headline=insight.headline,
            body=insight.body,
            side=insight.side,
            player_id=insight.player_id,
            evidence_event_ids=insight.evidence,
            claims=insight.claims,
            slots=insight.slots,
            tags=insight.tags,
        )
        self.aired.append(cue)
        return cue

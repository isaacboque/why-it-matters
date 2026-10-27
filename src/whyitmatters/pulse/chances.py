"""Shot types from the pass that set the shot up.

All in the shooting team's coordinates (attacking left to right, x = 105 the opponent's goal).
The assist is the event right before the shot, when it is a completed pass by the same team
to the shooter. A shot with no such pass is a carry, a rebound or a solo effort.

- cut-back: the pass starts by the goal line (x >= 94) in a wide lane and goes back (at least
  3 m) into the penalty area
- cross: a pass from the final third in a wide lane that ends in the penalty area
- through ball: a pass that breaks the opponent's back line (pulse/damage.py)
- long shot: none of the above and the shot is taken from 25 m or more
- other: everything else (a short pass, a carry, a rebound)

Wide = outside the middle third of the width. Big chance = xG of 0.3 or more.
"""

from __future__ import annotations

from whyitmatters.pulse import damage
from whyitmatters.schema import Event, EventType, Outcome

BYLINE_X = 94.0
CUTBACK_BACK_M = 3.0
LONG_SHOT_M = 25.0
BIG_CHANCE_XG = 0.3
SHOT_KINDS = ("cutback", "cross", "through", "long", "other")


def _wide(y: float) -> bool:
    return y < damage.THIRD_Y[0] or y >= damage.THIRD_Y[1]


def assist_of(prev: Event | None, shot: Event) -> Event | None:
    """The completed pass by the shooter's team that found the shooter, if it came right before."""
    if (
        prev is not None
        and prev.type == EventType.PASS
        and prev.outcome == Outcome.COMPLETE
        and prev.side == shot.side
        and prev.end_x is not None
        and prev.receiver_id is not None
        and prev.receiver_id == shot.player_id
    ):
        return prev
    return None


def shot_kind(prev: Event | None, shot: Event) -> str:
    """cutback / cross / through / long / other, from the pass before the shot."""
    p = assist_of(prev, shot)
    if p is not None:
        if (
            p.x >= BYLINE_X
            and _wide(p.y)
            and damage.in_box(p.end_x, p.end_y)
            and p.x - p.end_x >= CUTBACK_BACK_M
        ):
            return "cutback"
        if p.x >= damage.FINAL_THIRD_X and _wide(p.y) and damage.in_box(p.end_x, p.end_y):
            return "cross"
        if "back" in damage.lines_broken_roles(p):
            return "through"
    if damage.goal_distance(shot.x, shot.y) >= LONG_SHOT_M:
        return "long"
    return "other"

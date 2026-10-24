"""Build-up of a shot: how the move that ended in it began.

Used twice on purpose: the Analyst/Explainer cite it in a goal's "why", and the Verifier
recomputes it from the raw log before the claim airs. Definitions:

- the move is every event carrying the shot's possession id
- it began with a *recovery* when the event right before it is a tackle won or an interception
  by the shooting team
- *counter-press*: that recovery came within 5 s of the same team losing the ball
- *high recovery*: that recovery happened at x >= 52.5 (the opponent's half)
- *long balls*: completed passes of >= 30 m by the shooting team inside the move
"""

from __future__ import annotations

from dataclasses import dataclass

from whyitmatters.pulse.metrics import COUNTER_PRESS_S, HALF_X, LONG_BALL_M, is_recovery
from whyitmatters.schema import Event, EventType, Outcome

MAX_MOVE_S = 20.0  # a move longer than this is not "straight from the recovery"
MIN_MOVE_S = 2.0  # ... and a move this short is a deflection, not a move worth narrating


@dataclass(frozen=True)
class BuildUp:
    recovery: Event | None
    seconds: float | None  # recovery -> shot
    high_recovery: bool
    counter_press: bool
    long_balls: int


def _index_of(log: list[Event], shot: Event) -> int:
    i = shot.seq - 1
    if 0 <= i < len(log) and log[i].id == shot.id:
        return i
    return next(k for k, e in enumerate(log) if e.id == shot.id)


def analyse_buildup(log: list[Event], shot: Event) -> BuildUp:
    end = _index_of(log, shot)
    first = end
    while first > 0 and log[first - 1].possession_id == shot.possession_id:
        first -= 1
    move = log[first : end + 1]
    long_balls = sum(
        e.type == EventType.PASS
        and e.side == shot.side
        and e.outcome == Outcome.COMPLETE
        and (e.pass_distance or 0.0) >= LONG_BALL_M
        for e in move
    )
    rec = log[first - 1] if first > 0 else None
    if rec is None or not is_recovery(rec) or rec.side != shot.side:
        return BuildUp(None, None, False, False, long_balls)
    seconds = round(shot.t - rec.t, 1)
    # did the shooting team lose the ball just before winning it back?
    counter = False
    for e in reversed(log[: first - 1]):
        if rec.t - e.t > COUNTER_PRESS_S:
            break
        lost = (is_recovery(e) and e.side != shot.side) or (
            e.type == EventType.BALL_OUT and e.side == shot.side
        )
        if lost:
            counter = True
            break
    return BuildUp(rec, seconds, rec.x >= HALF_X, counter, long_balls)

"""Which passes hurt: line-breaking passes, packing, receptions between the lines, zone entries.

All in the passing team's coordinates (attacking left to right, x = 105 the opponent's goal).
The opponents' positions come from the pass's freeze frame (`ev.freeze.o`, index 0 = their
goalkeeper), so every number here can be recomputed from the raw event log.

- packing: opponent outfield players the pass takes out of the game, i.e. standing goal-side
  of the passer when it is played and behind the point where it is received
  (start x < opponent x < end x). After Impect's "packing" idea, counted on one frame.
- line-breaking pass: a completed pass that ends at least 10 % closer to the centre of goal
  and goes past at least one of the opponent's lines (a line's mean depth lies between the
  start and the end of the pass). After Hudl StatsBomb's definition, simplified to lines
  detected on the frame with pulse/shape.py.
- reception between the lines: a completed pass received between the opponent's back line and
  the line in front of it.
- zone 14: the central strip just outside the box (70 <= x < 88.5, middle third of the width);
  half-spaces: the strips between the box's edge and the middle third, in the final third;
  box: x >= 88.5 and 13.84 <= y <= 54.16.
- lanes: thirds of the width from the attacking team's point of view, with y = 0 on its left
  (the app draws y = 0 at the top and every team attacks to the right).
"""

from __future__ import annotations

import math

from whyitmatters.pulse.shape import detect_lines
from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, Event, EventType, Outcome

CLOSER_SHARE = 0.10  # a line-breaking pass ends this much closer to goal
BOX_X = 88.5
BOX_Y = (13.84, 54.16)
THIRD_Y = (PITCH_WIDTH / 3, 2 * PITCH_WIDTH / 3)
FINAL_THIRD_X = 70.0
LANES = ("left", "centre", "right")


def lane_of(y: float) -> str:
    return "left" if y < THIRD_Y[0] else "centre" if y < THIRD_Y[1] else "right"


def goal_distance(x: float, y: float) -> float:
    return math.hypot(PITCH_LENGTH - x, PITCH_WIDTH / 2 - y)


def is_completed_pass(ev: Event) -> bool:
    return ev.type == EventType.PASS and ev.outcome == Outcome.COMPLETE and ev.end_x is not None


def opponent_lines(ev: Event) -> list[float]:
    """Mean depth of each opponent line in the passer's coordinates, their back line first."""
    if ev.freeze is None:
        return []
    theirs = [(PITCH_LENGTH - x, PITCH_WIDTH - y) for x, y in ev.freeze.o[1:]]
    lines = detect_lines(theirs)
    return [PITCH_LENGTH - sum(theirs[i][0] for i in ln) / len(ln) for ln in lines]


def packing(ev: Event) -> int:
    """Opponent outfield players a completed pass goes past (0 for anything else)."""
    if not is_completed_pass(ev) or ev.freeze is None:
        return 0
    lo, hi = ev.x, ev.end_x
    return sum(1 for x, _ in ev.freeze.o[1:] if lo < x < hi)


def lines_broken(ev: Event) -> int:
    """How many opponent lines a completed, goalward pass goes past."""
    if not is_completed_pass(ev):
        return 0
    if goal_distance(ev.end_x, ev.end_y) > (1 - CLOSER_SHARE) * goal_distance(ev.x, ev.y):
        return 0
    return sum(1 for lx in opponent_lines(ev) if ev.x < lx < ev.end_x)


def between_lines(ev: Event) -> bool:
    """A completed pass received between the opponent's back line and the next line."""
    if not is_completed_pass(ev):
        return False
    lines = opponent_lines(ev)
    if len(lines) < 2:
        return False
    back, next_line = lines[0], lines[1]
    return next_line < ev.end_x < back


def in_box(x: float, y: float) -> bool:
    return x >= BOX_X and BOX_Y[0] <= y <= BOX_Y[1]


def in_zone14(x: float, y: float) -> bool:
    return FINAL_THIRD_X <= x < BOX_X and THIRD_Y[0] <= y < THIRD_Y[1]


def in_half_space(x: float, y: float) -> bool:
    return x >= FINAL_THIRD_X and (BOX_Y[0] <= y < THIRD_Y[0] or THIRD_Y[1] <= y <= BOX_Y[1])


def entries(ev: Event) -> tuple[bool, bool, bool]:
    """(box, zone 14, half-space) entries made by a completed pass or a carry."""
    moved = is_completed_pass(ev) or (ev.type == EventType.CARRY and ev.end_x is not None)
    if not moved:
        return False, False, False
    ex, ey = ev.end_x, ev.end_y
    return (
        in_box(ex, ey) and not in_box(ev.x, ev.y),
        in_zone14(ex, ey) and not in_zone14(ev.x, ev.y),
        in_half_space(ex, ey) and not in_half_space(ev.x, ev.y),
    )

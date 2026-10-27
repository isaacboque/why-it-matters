"""Which passes hurt: line-breaking passes, packing, receptions between the lines, zone entries.

All in the passing team's coordinates (attacking left to right, x = 105 the opponent's goal).
The opponents' positions come from the pass's freeze frame (`ev.freeze.o`, index 0 = their
goalkeeper), so every number here can be recomputed from the raw event log.

- packing: opponent outfield players the pass takes out of the game, i.e. standing goal-side
  of the passer when it is played and behind the point where it is received
  (start x < opponent x < end x). After Impect's "packing" idea, counted on one frame.
- line-breaking pass: a completed pass that ends at least 10 % closer to the centre of goal
  and goes through at least one of the opponent's lines: the pass segment crosses the line's
  mean depth at a y inside the line's lateral span (outermost players, +- 2 m). Passes round
  the side of a line do not count. Reported per line broken (back, midfield, forward). After
  Hudl StatsBomb's definition, simplified to lines detected on one frame with pulse/shape.py.
- reception between the lines: a completed pass received between ANY two consecutive opponent
  lines (midfield-defence, press-midfield, and the extra gap when 4 lines are detected),
  inside the lateral span of the two lines (+- 2 m) and at least 3 m from every opponent in
  the frame (a reception in space).
- zone 14: the central strip just outside the box (70 <= x < 88.5, middle third of the width);
  half-spaces: the strips between the box's edge and the middle third, in the final third;
  box: x >= 88.5 and 13.84 <= y <= 54.16.
- lanes: thirds of the width from the attacking team's point of view, with y = 0 on its left
  (the app draws y = 0 at the top and every team attacks to the right).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from whyitmatters.pulse.shape import detect_lines
from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, Event, EventType, Outcome

CLOSER_SHARE = 0.10  # a line-breaking pass ends this much closer to goal
LINE_SPAN_MARGIN_M = 2.0  # a line spans its outermost players' y, plus this much each side
RECEPTION_SPACE_M = 3.0  # a reception "in space" is at least this far from every opponent
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


class Line(NamedTuple):
    """One opponent line from the freeze frame, in the passer's coordinates."""

    depth: float  # mean x of its players
    y_min: float  # lateral span: outermost players
    y_max: float


def opponent_line_shapes(ev: Event) -> list[Line]:
    """The opponent's lines (3-4, forced by `detect_lines`), their back line first.

    Lines come from one freeze frame, so they are a snapshot of the block, not a tracked unit.
    """
    if ev.freeze is None:
        return []
    theirs = [(PITCH_LENGTH - x, PITCH_WIDTH - y) for x, y in ev.freeze.o[1:]]
    out = []
    for ln in detect_lines(theirs):
        ys = [PITCH_WIDTH - theirs[i][1] for i in ln]
        out.append(Line(PITCH_LENGTH - sum(theirs[i][0] for i in ln) / len(ln), min(ys), max(ys)))
    return out


def opponent_lines(ev: Event) -> list[float]:
    """Mean depth of each opponent line in the passer's coordinates, their back line first."""
    return [ln.depth for ln in opponent_line_shapes(ev)]


def line_role(index: int, n_lines: int) -> str:
    """Name of line `index` (0 = back line): back, midfield (any in between) or forward."""
    return "back" if index == 0 else "forward" if index == n_lines - 1 else "midfield"


def packing(ev: Event) -> int:
    """Opponent outfield players a completed pass goes past (0 for anything else)."""
    if not is_completed_pass(ev) or ev.freeze is None:
        return 0
    lo, hi = ev.x, ev.end_x
    return sum(1 for x, _ in ev.freeze.o[1:] if lo < x < hi)


def lines_broken_roles(ev: Event) -> list[str]:
    """Which opponent lines a completed, goalward pass breaks: back, midfield, forward.

    A line is broken when the pass segment crosses the line's depth inside its lateral span.
    """
    if not is_completed_pass(ev):
        return []
    if goal_distance(ev.end_x, ev.end_y) > (1 - CLOSER_SHARE) * goal_distance(ev.x, ev.y):
        return []
    lines = opponent_line_shapes(ev)
    dx = ev.end_x - ev.x
    roles = []
    for i, ln in enumerate(lines):
        if not ev.x < ln.depth < ev.end_x:
            continue
        y = ev.y + (ln.depth - ev.x) / dx * (ev.end_y - ev.y)
        if ln.y_min - LINE_SPAN_MARGIN_M <= y <= ln.y_max + LINE_SPAN_MARGIN_M:
            roles.append(line_role(i, len(lines)))
    return roles


def lines_broken(ev: Event) -> int:
    """How many opponent lines a completed, goalward pass goes through."""
    return len(lines_broken_roles(ev))


def reception_gaps(ev: Event) -> list[str]:
    """The gaps between consecutive opponent lines a completed pass is received in, in space.

    Gap names: "mid_def" (between midfield and defence, back-most gap), "fwd_mid" (between the
    press and midfield, front-most gap) and "inner" (the extra gap when 4 lines are detected).
    The reception must be inside the two lines' lateral span and RECEPTION_SPACE_M from every
    opponent in the frame. The ball cannot be in two gaps, so the list has at most one entry.
    """
    if not is_completed_pass(ev) or ev.freeze is None:
        return []
    lines = opponent_line_shapes(ev)
    ex, ey = ev.end_x, ev.end_y
    if any(math.hypot(ex - ox, ey - oy) < RECEPTION_SPACE_M for ox, oy in ev.freeze.o):
        return []
    for i in range(len(lines) - 1):
        back, front = lines[i], lines[i + 1]
        if not front.depth < ex < back.depth:
            continue
        lo = min(back.y_min, front.y_min) - LINE_SPAN_MARGIN_M
        hi = max(back.y_max, front.y_max) + LINE_SPAN_MARGIN_M
        if not lo <= ey <= hi:
            return []
        if i == 0:
            return ["mid_def"]
        return ["fwd_mid"] if i == len(lines) - 2 else ["inner"]
    return []


def between_lines(ev: Event) -> bool:
    """A completed pass received in space between any two consecutive opponent lines."""
    return bool(reception_gaps(ev))


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

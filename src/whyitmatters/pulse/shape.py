"""Team shape from freeze frames: average positions, formation, line height, gaps, compactness.

Everything here works on AVERAGE positions over a window, in the team's own coordinates
(attacking left to right). Averaging removes the ball-driven sway, so what is left is the
structure a coach would draw: which lines the team forms, how high the back line stands,
how far apart the lines are and how much grass the team covers.

Formation detection is line-based and needs no template: sort the 10 outfield players by
depth, start a new line wherever the gap to the next player exceeds LINE_GAP_M, then merge
or split to keep 3-4 lines. The label counts players per line from back to front ("4-4-2").
"""

from __future__ import annotations

from pydantic import BaseModel

from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, Event, EventType, Side

LINE_GAP_M = 7.5
MIN_FRAMES = 8  # frames needed in a window before a shape is reported
DEFENDING_TYPES = {EventType.PRESSURE, EventType.TACKLE, EventType.INTERCEPTION, EventType.FOUL}

# Block type from the out-of-possession back-line height (metres from own goal), averaged
# over a window. Thresholds set on simulator seeds 0-39; see docs/METHODS.md.
BLOCK_HIGH_M = 30.0
BLOCK_LOW_M = 20.0

Pos = tuple[float, float]


def possession_side(ev: Event) -> Side:
    """Which team has the ball at this event (defensive actions are made without it)."""
    if ev.type in DEFENDING_TYPES:
        return "away" if ev.side == "home" else "home"
    return ev.side


def own_frame(ev: Event, side: Side) -> list[Pos] | None:
    """A team's 11 positions at an event, in that team's own coordinates."""
    if ev.freeze is None:
        return None
    if side == ev.side:
        return [tuple(p) for p in ev.freeze.t]  # type: ignore[misc]
    return [(PITCH_LENGTH - x, PITCH_WIDTH - y) for x, y in ev.freeze.o]


def detect_lines(outfield: list[Pos]) -> list[list[int]]:
    """Group outfield players (indices into `outfield`) into lines, back to front."""
    order = sorted(range(len(outfield)), key=lambda i: outfield[i][0])
    lines: list[list[int]] = [[order[0]]]
    for a, b in zip(order, order[1:], strict=False):
        if outfield[b][0] - outfield[a][0] > LINE_GAP_M:
            lines.append([b])
        else:
            lines[-1].append(b)

    def mean_x(line: list[int]) -> float:
        return sum(outfield[i][0] for i in line) / len(line)

    while len(lines) > 4:  # merge the two closest neighbouring lines
        gaps = [mean_x(lines[k + 1]) - mean_x(lines[k]) for k in range(len(lines) - 1)]
        k = gaps.index(min(gaps))
        lines[k : k + 2] = [lines[k] + lines[k + 1]]
    while len(lines) < 3:  # split the deepest line at its largest internal gap
        k = max(range(len(lines)), key=lambda j: len(lines[j]))
        ln = sorted(lines[k], key=lambda i: outfield[i][0])
        gaps = [outfield[ln[j + 1]][0] - outfield[ln[j]][0] for j in range(len(ln) - 1)]
        if not gaps:
            break
        cut = gaps.index(max(gaps)) + 1
        lines[k : k + 1] = [ln[:cut], ln[cut:]]
    return lines


def hull_area(points: list[Pos]) -> float:
    """Area of the convex hull (m^2), Andrew's monotone chain + shoelace."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def cross(o: Pos, a: Pos, b: Pos) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Pos] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Pos] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for i, (x1, y1) in enumerate(hull):
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


class ShapeSummary(BaseModel):
    formation: str
    line_height: float  # back line, metres from own goal
    gap_def_mid: float  # metres between the back line and the next line
    gap_mid_att: float  # metres between the last two lines
    length: float  # deepest to highest outfield player
    width: float
    compactness: float  # convex hull area of the outfield players, m^2
    avg: list[tuple[float, float]]  # all 11 average positions, own coordinates


def summarize(avg: list[Pos]) -> ShapeSummary:
    """Shape of a team from its 11 average positions (index 0 = goalkeeper)."""
    outfield = avg[1:]
    lines = detect_lines(outfield)

    def mean_x(line: list[int]) -> float:
        return sum(outfield[i][0] for i in line) / len(line)

    xs = [p[0] for p in outfield]
    ys = [p[1] for p in outfield]
    return ShapeSummary(
        formation="-".join(str(len(ln)) for ln in lines),
        line_height=round(mean_x(lines[0]), 1),
        gap_def_mid=round(mean_x(lines[1]) - mean_x(lines[0]), 1),
        gap_mid_att=round(mean_x(lines[-1]) - mean_x(lines[-2]), 1),
        length=round(max(xs) - min(xs), 1),
        width=round(max(ys) - min(ys), 1),
        compactness=round(hull_area(outfield), 0),
        avg=[(round(x, 1), round(y, 1)) for x, y in avg],
    )


def block_of(line_height: float) -> str:
    if line_height >= BLOCK_HIGH_M:
        return "high"
    if line_height < BLOCK_LOW_M:
        return "low"
    return "mid"


def formation_code(label: str) -> float:
    """A formation as a number a Claim can carry: '4-4-2' -> 442.0 (formatted back by fmt)."""
    return float("".join(label.split("-")))

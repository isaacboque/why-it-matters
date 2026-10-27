"""Freeze frames: where all 22 players stand at every on-ball event.

A post-pass over the finished event list (it never touches the event generator's random
stream, so the events themselves are unchanged). Each team has a role per phase (dominant,
dominated, balanced, chaotic), and each role has an in-possession shape, an out-of-possession
shape, a defensive-line height, a width and a gap between lines. Targets follow the ball
(longitudinal and lateral shift), players move towards them at a capped speed, and small
noise keeps it from looking drawn with a ruler.

Frames are stored on each event in the ACTING team's coordinates (like the event itself):
`t` = the acting team's 11 players, `o` = the opponents, both in the team's `players` order.
The scripted shapes are written to the ground truth so shape detection can be evaluated.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from whyitmatters.schema import (
    PITCH_LENGTH,
    PITCH_WIDTH,
    Event,
    EventType,
    Freeze,
    Phase,
    ShapeTruth,
    Side,
    Team,
)
from whyitmatters.simulator.phases import game_state, phase_at
from whyitmatters.simulator.teams import CLUB_IDENTITY

# Slot key = position + shirt number, as in teams.FORMATION_433
SLOTS = ("GK1", "RB2", "CB4", "CB5", "LB3", "DM6", "CM8", "CM10", "RW7", "ST9", "LW11")


@dataclass(frozen=True)
class RoleShape:
    in_possession: str  # formation label, lines from back to front
    out_of_possession: str
    block: str  # high / mid / low
    line_out: float  # out-of-possession back line, metres from own goal
    line_in_cap: float  # how high the back line may push in possession
    gap: float  # metres between defensive lines out of possession
    width: float  # lateral scale around the centre line


ROLES: dict[str, RoleShape] = {
    "dominant": RoleShape("3-2-5", "4-4-2", "high", 46.0, 56.0, 11.0, 0.92),
    "dominated": RoleShape("4-3-3", "4-5-1", "low", 22.0, 40.0, 9.0, 0.80),
    "balanced": RoleShape("4-3-3", "4-4-2", "mid", 34.0, 46.0, 11.0, 0.88),
    "chaotic": RoleShape("4-3-3", "4-4-2", "high", 42.0, 50.0, 17.0, 0.95),
}

PHASE_ROLES: dict[str, dict[Side, str]] = {
    "home_control": {"home": "dominant", "away": "dominated"},
    "away_control": {"home": "dominated", "away": "dominant"},
    "balanced": {"home": "balanced", "away": "balanced"},
    "chaos": {"home": "chaotic", "away": "chaotic"},
}

# In-possession templates: (depth in front of the back line, y)
IN_SHAPES: dict[str, dict[str, tuple[float, float]]] = {
    "4-3-3": {
        "RB2": (6, 62), "CB4": (0, 46), "CB5": (0, 22), "LB3": (6, 6), "DM6": (16, 34),
        "CM8": (20, 48), "CM10": (20, 20), "RW7": (38, 63), "ST9": (42, 34), "LW11": (38, 5),
    },
    "3-2-5": {
        "CB4": (0, 50), "CB5": (0, 34), "LB3": (0, 18), "RB2": (14, 42), "DM6": (14, 26),
        "RW7": (38, 64), "CM8": (36, 46), "ST9": (42, 34), "CM10": (36, 22), "LW11": (38, 4),
    },
}


def out_shape(label: str, gap: float) -> dict[str, tuple[float, float]]:
    """Out-of-possession templates, built from the gap between lines."""
    back = {"RB2": (0, 58), "CB4": (0, 41), "CB5": (0, 27), "LB3": (0, 10)}
    if label == "4-5-1":
        return back | {
            "RW7": (gap, 60), "CM8": (gap, 46), "DM6": (gap - 2, 34), "CM10": (gap, 22),
            "LW11": (gap, 8), "ST9": (2 * gap + 2, 34),
        }
    return back | {  # 4-4-2
        "RW7": (gap, 58), "CM8": (gap, 42), "DM6": (gap, 26), "LW11": (gap, 10),
        "ST9": (2 * gap, 40), "CM10": (2 * gap, 28),
    }


MAX_SPEED = 8.5  # m/s, how far a player can move towards his target between frames
# Fatigue: from FATIGUE_FROM_MIN a team closes less of the distance to its target between frames,
# down to 1 - rate at full time. Pressing clubs tire most. Scripted ground truth for the
# physical_drop insight; the event stream and the random stream are untouched.
FATIGUE_FROM_MIN = 60.0
FATIGUE_RATE = {
    "HBC": 0.34, "CRB": 0.30, "NBA": 0.22, "ASH": 0.18, "RVM": 0.20, "WHA": 0.20,
    "KFR": 0.14, "ELW": 0.14,
}  # fmt: skip
PERSISTENT_SD = 1.2
JITTER_SD = 0.8
DEFENDING_TYPES = {EventType.PRESSURE, EventType.TACKLE, EventType.INTERCEPTION, EventType.FOUL}


def fatigue(short_name: str, minute: float) -> float:
    """Share of the way to its target a team's players get late in the match (1 = fresh)."""
    late = min(max((minute - FATIGUE_FROM_MIN) / (90.0 - FATIGUE_FROM_MIN), 0.0), 1.0)
    return 1.0 - FATIGUE_RATE.get(short_name, 0.2) * late


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


def possession_side(ev: Event) -> Side:
    """Which team has the ball at this event (defensive actions are made without it)."""
    return _other(ev.side) if ev.type in DEFENDING_TYPES else ev.side


def role_at(phases: list[Phase], minute: float, side: Side) -> str:
    return PHASE_ROLES[phase_at(phases, minute).kind][side]


def _clip(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def team_targets(
    team: Team, role: RoleShape, in_possession: bool, ball: tuple[float, float],
    shift: float = 0.0,
) -> list[tuple[float, float]]:
    """Target positions for a team, in its own coordinates, given the ball (own coordinates)."""
    bx, by = ball
    if in_possession:
        line = _clip(bx - 25.0, 12.0, role.line_in_cap + shift)
        tmpl = IN_SHAPES[role.in_possession]
        lateral = 0.20
    else:
        # the back line holds its height, but never stands in front of a ball near its goal
        line = min(role.line_out + shift, max(6.0, bx - 10.0))
        tmpl = out_shape(role.out_of_possession, role.gap)
        lateral = 0.35
    shift_y = (by - PITCH_WIDTH / 2) * lateral
    out = []
    for p in team.players:
        key = f"{p.position}{p.number}"
        if key == "GK1":
            gx = 5.0 if not in_possession else _clip(line - 25.0, 4.0, 14.0)
            out.append((gx, PITCH_WIDTH / 2 + (by - PITCH_WIDTH / 2) * 0.15))
            continue
        depth, y = tmpl[key]
        x = _clip(line + depth, 2.0, PITCH_LENGTH - 2.0)
        y = PITCH_WIDTH / 2 + (y - PITCH_WIDTH / 2) * role.width + shift_y
        out.append((x, _clip(y, 1.0, PITCH_WIDTH - 1.0)))
    return out


def _to_home(side: Side, x: float, y: float) -> tuple[float, float]:
    return (x, y) if side == "home" else (PITCH_LENGTH - x, PITCH_WIDTH - y)


def add_freeze_frames(
    events: list[Event], teams: dict[Side, Team], phases: list[Phase], seed: int
) -> list[ShapeTruth]:
    """Attach a freeze frame to every on-ball event; return the scripted shapes per phase."""
    rng = random.Random(seed * 7919 + 17)
    offsets = {
        side: [(rng.gauss(0, PERSISTENT_SD), rng.gauss(0, PERSISTENT_SD)) for _ in t.players]
        for side, t in teams.items()
    }
    # positions in HOME coordinates, per side, in players order
    pos: dict[Side, list[tuple[float, float]] | None] = {"home": None, "away": None}
    last_t: float | None = None

    for ev in events:
        if ev.type == EventType.HALF_END:
            pos = {"home": None, "away": None}
            last_t = None
            continue
        dt = 0.5 if last_t is None else max(0.5, ev.t - last_t)
        last_t = ev.t
        holder = possession_side(ev)
        # the ball in each team's own coordinates
        ball_home = _to_home(ev.side, ev.x, ev.y)
        for side in ("home", "away"):
            role = ROLES[role_at(phases, ev.t / 60.0, side)]
            ball_own = _to_home(side, *ball_home)  # home->own is the same mirror
            # club identity and game state move the block (a leader drops, a trailer pushes up)
            diff = (ev.score_home - ev.score_away) * (1 if side == "home" else -1)
            shift = CLUB_IDENTITY[teams[side].short_name].line + game_state(diff, ev.t / 60.0)[3]
            targets = team_targets(teams[side], role, side == holder, ball_own, shift)
            new = []
            tire = fatigue(teams[side].short_name, ev.t / 60.0)
            for i, (tx, ty) in enumerate(targets):
                ox, oy = offsets[side][i]
                tx, ty = _to_home(side, tx + ox, ty + oy)
                prev = pos[side][i] if pos[side] is not None else None
                if prev is None or ev.type == EventType.KICK_OFF:
                    nx, ny = tx, ty
                else:
                    step = MAX_SPEED * dt
                    dx, dy = tx - prev[0], ty - prev[1]
                    d = math.hypot(dx, dy)
                    k = (1.0 if d <= step else step / d) * tire
                    nx, ny = prev[0] + dx * k, prev[1] + dy * k
                nx += rng.gauss(0, JITTER_SD)
                ny += rng.gauss(0, JITTER_SD)
                new.append((_clip(nx, 0.5, PITCH_LENGTH - 0.5), _clip(ny, 0.5, PITCH_WIDTH - 0.5)))
            pos[side] = new
        # the acting player stands exactly where the event happens
        if ev.player_id:
            idx = next(
                (i for i, p in enumerate(teams[ev.side].players) if p.id == ev.player_id), None
            )
            if idx is not None:
                pos[ev.side][idx] = ball_home  # type: ignore[index]
        # store in the acting team's coordinates
        me, opp = ev.side, _other(ev.side)
        ev.freeze = Freeze(
            t=[_r(_to_home(me, *p)) for p in pos[me]],  # type: ignore[union-attr]
            o=[_r(_to_home(me, *p)) for p in pos[opp]],  # type: ignore[union-attr]
        )

    truth: list[ShapeTruth] = []
    for ph in phases:
        for side in ("home", "away"):
            r = ROLES[PHASE_ROLES[ph.kind][side]]
            truth.append(
                ShapeTruth(
                    side=side,
                    start_minute=ph.start_minute,
                    end_minute=ph.end_minute,
                    in_possession=r.in_possession,
                    out_of_possession=r.out_of_possession,
                    block=r.block,
                )
            )
    return truth


def _r(p: tuple[float, float]) -> tuple[float, float]:
    return (round(p[0], 1), round(p[1], 1))

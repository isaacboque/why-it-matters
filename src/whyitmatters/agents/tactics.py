"""Tactical insight detectors, run on every closed minute of the Match Pulse.

Each looks at the latest 5-minute window against the 5 minutes before it and fires only on a
clear, one-sided swing (so it adds a reason rather than repeating "chaos"):

- press_surge:      a team wins the ball high up the pitch and squeezes its opponent's build-up
- midfield_battle:  a team wins most of the midfield duels (over a real sample)
- danger_turnovers: a team keeps losing the ball in its own half, far more than the other
- direct_switch:    a team starts going long while the other side presses it

Damage and shape (freeze frames and Expected Threat; pulse/damage.py, pulse/shape.py, pulse/xt.py):

- line_breakers:       a team starts playing through the opponent's lines, far more than the other
- zone_damage:         most of a team's threat comes down one lane (left, centre or right)
- momentum_swing:      the side creating more threat flips
- shape_change:        a team changes its shape in possession (over 8-minute windows, so a few
                       odd frames do not count)
- lines_stretched:     the gap between a team's back line and midfield opens up
- most_dangerous_pass: one completed pass adds a lot of threat and takes players out of the game

Thresholds were set on seeds 0-39; the held-out check is the insight-per-match table in README.
"""

from __future__ import annotations

from collections.abc import Callable

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.models import InsightCandidate, InsightKind
from whyitmatters.pulse import damage
from whyitmatters.pulse import xt as xt_model
from whyitmatters.pulse.engine import PulseSnapshot
from whyitmatters.pulse.metrics import (
    FINAL_THIRD_X,
    HALF_X,
    LONG_BALL_M,
    TeamWindow,
    WindowMetrics,
    duel_winner,
    is_recovery,
)
from whyitmatters.schema import PITCH_LENGTH, Event, EventType, Side

WINDOW = 5
FIRST_MINUTE = 9  # need a full window plus the one before it

PRESS_MIN_RECOVERIES = 5
PRESS_MIN_JUMP = 3
PRESS_RATIO = 0.5  # own PPDA must be at most this share of the opponent's

DUEL_MIN_TOTAL = 6
DUEL_SHARE = 0.65
DUEL_SHARE_BEFORE = 0.55

TURNOVER_MIN = 6
TURNOVER_RATIO = 2.5  # at least this many times the opponent's own-half losses
TURNOVER_MIN_JUMP = 3

DIRECT_SHARE = 0.16
DIRECT_SHARE_BEFORE = 0.09
DIRECT_MIN_PASSES = 15
DIRECT_MAX_OPP_PPDA = 6.0

LINE_BREAKS_MIN = 9
LINE_BREAKS_LEAD = 4  # more than the opponent in the same window
LINE_BREAKS_JUMP = 4  # more than the same team in the window before

ZONE_MIN_XT = 0.15
ZONE_SHARE = 0.6  # down a flank
ZONE_SHARE_CENTRE = 0.8  # most threat goes through the middle anyway, so ask for more
ZONE_XT_RATIO = 1.5  # at least this many times the opponent's threat

MOMENTUM_LEAD = 0.12  # xT ahead now...
MOMENTUM_BEHIND = 0.05  # ...after being at least this far behind in the window before

SHAPE_WINDOW = 8
SHAPE_STABLE_GAP = 2  # the window ending this much earlier must agree, before and after

STRETCH_GAP_M = 16.5
STRETCH_LENGTH_M = 33.0  # and the whole team is long: a gap alone can be a deep midfield
STRETCH_GROWTH_M = 3.0

DANGEROUS_PASS_XT = 0.09
DANGEROUS_PASS_PACKING = 3

COOLDOWN_MIN = {  # the same kind about the same team is not voiced again within this long
    "press_surge": 15,
    "midfield_battle": 20,
    "danger_turnovers": 15,
    "direct_switch": 20,
    "line_breakers": 15,
    "zone_damage": 20,
    "momentum_swing": 15,
    "shape_change": 30,
    "lines_stretched": 20,
    "most_dangerous_pass": 12,
}
ANY_TACTICAL_GAP_MIN = 6  # and at most one tactical insight every few minutes
AFTER_SHIFT_QUIET_MIN = 4  # a control shift has just said it; do not repeat it as a reason
SIGNIFICANCE = {
    "press_surge": 0.55,
    "midfield_battle": 0.5,
    "danger_turnovers": 0.5,
    "direct_switch": 0.45,
    "shape_change": 0.55,
    "line_breakers": 0.5,
    "momentum_swing": 0.5,
    "zone_damage": 0.45,
    "lines_stretched": 0.45,
    "most_dangerous_pass": 0.4,
}


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


def _team(w: WindowMetrics, side: Side) -> TeamWindow:
    return w.home if side == "home" else w.away


def _events_in(state: Blackboard, w: WindowMetrics, pred: Callable[[Event], bool]) -> list[str]:
    """Ids of the window's events that satisfy `pred`, oldest first (at most six)."""
    found: list[str] = []
    for ev in reversed(state.log):
        if ev.minute > w.end_minute:
            continue
        if ev.minute < w.start_minute:
            break
        if pred(ev):
            found.append(ev.id)
    return found[:6][::-1]


# ---------------------------------------------------------------------- evidence predicates
def _high_recovery_by(side: Side) -> Callable[[Event], bool]:
    return lambda e: is_recovery(e) and e.side == side and e.x >= HALF_X


def _mid_duel(e: Event) -> bool:
    d = duel_winner(e)
    return d is not None and 35.0 <= d[1] < FINAL_THIRD_X


def _own_half_loss_by(side: Side) -> Callable[[Event], bool]:
    """The ball is lost by `side` in its own half: won off it, or put out of play."""

    def pred(e: Event) -> bool:
        if is_recovery(e) and e.side != side:
            return (PITCH_LENGTH - e.x) < HALF_X
        return e.type == EventType.BALL_OUT and e.side == side and e.x < HALF_X

    return pred


def _long_pass_by(side: Side) -> Callable[[Event], bool]:
    return lambda e: (
        e.type == EventType.PASS and e.side == side and (e.pass_distance or 0.0) >= LONG_BALL_M
    )


# ---------------------------------------------------------------------- rules
def press_surge(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    if me.high_recoveries < PRESS_MIN_RECOVERIES or me.ppda is None:
        return False
    if me.high_recoveries - was.high_recoveries < PRESS_MIN_JUMP:
        return False
    return me.ppda <= PRESS_RATIO * (opp.ppda if opp.ppda is not None else 99.0)


def midfield_battle(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    if me.duels_won_mid + opp.duels_won_mid < DUEL_MIN_TOTAL or me.duel_share_mid is None:
        return False
    before_ok = was.duel_share_mid is None or was.duel_share_mid < DUEL_SHARE_BEFORE
    return me.duel_share_mid >= DUEL_SHARE and before_ok


def danger_turnovers(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    return (
        me.own_half_losses >= TURNOVER_MIN
        and me.own_half_losses >= TURNOVER_RATIO * max(opp.own_half_losses, 1)
        and me.own_half_losses - was.own_half_losses >= TURNOVER_MIN_JUMP
    )


def direct_switch(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    return (
        me.passes >= DIRECT_MIN_PASSES
        and me.long_ball_share >= DIRECT_SHARE
        and was.long_ball_share <= DIRECT_SHARE_BEFORE
        and opp.ppda is not None
        and opp.ppda <= DIRECT_MAX_OPP_PPDA
    )


def line_breakers(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    return (
        me.line_breaks >= LINE_BREAKS_MIN
        and me.line_breaks - opp.line_breaks >= LINE_BREAKS_LEAD
        and me.line_breaks - was.line_breaks >= LINE_BREAKS_JUMP
    )


def damage_lane(me: TeamWindow) -> str | None:
    """The lane (left / centre / right) most of a team's threat comes down, if one dominates."""
    shares = {
        "left": me.xt_share_left or 0.0,
        "centre": me.xt_share_centre or 0.0,
        "right": me.xt_share_right or 0.0,
    }
    lane = max(shares, key=shares.__getitem__)
    need = ZONE_SHARE_CENTRE if lane == "centre" else ZONE_SHARE
    return lane if shares[lane] >= need else None


def zone_damage(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    return (
        me.xt >= ZONE_MIN_XT
        and me.xt >= ZONE_XT_RATIO * max(opp.xt, 0.0)
        and damage_lane(me) is not None
    )


def momentum_swing(me: TeamWindow, opp: TeamWindow, was: TeamWindow, was_opp: TeamWindow) -> bool:
    return me.xt - opp.xt >= MOMENTUM_LEAD and was_opp.xt - was.xt >= MOMENTUM_BEHIND


def lines_stretched(me: TeamWindow, opp: TeamWindow, was: TeamWindow) -> bool:
    if me.gap_def_mid is None or was.gap_def_mid is None or me.team_length is None:
        return False
    return (
        me.gap_def_mid >= STRETCH_GAP_M
        and me.team_length >= STRETCH_LENGTH_M
        and me.gap_def_mid - was.gap_def_mid >= STRETCH_GROWTH_M
    )


def shape_changed(state: Blackboard, minute: int, side: Side) -> bool:
    """The in-possession shape over the last 8 minutes differs from the 8 before, and both
    readings are stable (the windows ending two minutes earlier agree with them)."""
    if minute - 2 * SHAPE_WINDOW - SHAPE_STABLE_GAP < 0:
        return False
    counter = state.pulse.counter

    def f(end: int) -> float | None:
        return _team(counter.window(end, SHAPE_WINDOW), side).formation_in

    now, before = f(minute), f(minute - SHAPE_WINDOW)
    if now is None or before is None or now == before:
        return False
    return (
        f(minute - SHAPE_STABLE_GAP) == now
        and f(minute - SHAPE_WINDOW - SHAPE_STABLE_GAP) == before
    )


def _line_break_by(side: Side) -> Callable[[Event], bool]:
    return lambda e: e.side == side and damage.lines_broken(e) > 0


def _threat_in_lane(side: Side, lane: str) -> Callable[[Event], bool]:
    def pred(e: Event) -> bool:
        if e.side != side or e.end_x is None or e.type not in (EventType.PASS, EventType.CARRY):
            return False
        if e.type == EventType.PASS and not damage.is_completed_pass(e):
            return False
        return damage.lane_of(e.end_y) == lane and xt_model.added(e.x, e.y, e.end_x, e.end_y) > 0.02

    return pred


def _threat_by(side: Side) -> Callable[[Event], bool]:
    return lambda e: (
        e.side == side
        and damage.is_completed_pass(e)
        and xt_model.added(e.x, e.y, e.end_x, e.end_y) > 0.03
    )


def _passes_by(side: Side) -> Callable[[Event], bool]:
    """The team's own passes: their freeze frames show the shape in possession."""
    return lambda e: e.side == side and e.type == EventType.PASS


def _opponent_passes_against(side: Side) -> Callable[[Event], bool]:
    """The opponent's passes: their freeze frames show `side` out of possession."""
    return lambda e: e.side != side and e.type == EventType.PASS


class TacticsWatcher:
    def __init__(self, new_id: Callable[[], str]) -> None:
        self._new_id = new_id
        self._last: dict[tuple[str, Side], int] = {}
        self._last_any = -ANY_TACTICAL_GAP_MIN

    def run(
        self, state: Blackboard, snap: PulseSnapshot, now_t: float, last_shift: int = -99
    ) -> list[InsightCandidate]:
        minute = snap.minute
        if minute < FIRST_MINUTE or minute - self._last_any < ANY_TACTICAL_GAP_MIN:
            return []
        if minute - last_shift < AFTER_SHIFT_QUIET_MIN:
            return []
        now = snap.window
        before = state.pulse.counter.window(minute - WINDOW, WINDOW)
        found: list[tuple[InsightKind, Side, Callable[[Event], bool]]] = []
        shape_now = state.pulse.counter.window(minute, SHAPE_WINDOW)
        for side in ("home", "away"):
            me, opp, was = _team(now, side), _team(now, _other(side)), _team(before, side)
            was_opp = _team(before, _other(side))
            if shape_changed(state, minute, side):
                found.append(("shape_change", side, _passes_by(side)))
            if line_breakers(me, opp, was):
                found.append(("line_breakers", side, _line_break_by(side)))
            if momentum_swing(me, opp, was, was_opp):
                found.append(("momentum_swing", side, _threat_by(side)))
            if zone_damage(me, opp, was):
                found.append(("zone_damage", side, _threat_in_lane(side, damage_lane(me) or "")))
            if lines_stretched(me, opp, was):
                found.append(("lines_stretched", side, _opponent_passes_against(side)))
            if press_surge(me, opp, was):
                found.append(("press_surge", side, _high_recovery_by(side)))
            if midfield_battle(me, opp, was):
                found.append(("midfield_battle", side, _mid_duel))
            if danger_turnovers(me, opp, was):
                found.append(("danger_turnovers", side, _own_half_loss_by(side)))
            if direct_switch(me, opp, was):
                found.append(("direct_switch", side, _long_pass_by(side)))
        for kind, side, pred in sorted(found, key=lambda f: -SIGNIFICANCE[f[0]]):
            if minute - self._last.get((kind, side), -99) < COOLDOWN_MIN[kind]:
                continue
            self._last[(kind, side)] = minute
            self._last_any = minute
            w = shape_now if kind == "shape_change" else now
            return [
                InsightCandidate(
                    id=self._new_id(),
                    kind=kind,
                    minute=minute,
                    t=min((minute + 1) * 60.0, now_t),  # the last minute closes at full time
                    significance=SIGNIFICANCE[kind],
                    side=side,
                    window=(w.start_minute, w.end_minute),
                    evidence=_events_in(state, w, pred) or _events_in(state, w, _passes_by(side)),
                )
            ]  # one tactical insight per closed minute
        return self._dangerous_pass(state, minute, now_t)

    def _dangerous_pass(
        self, state: Blackboard, minute: int, now_t: float
    ) -> list[InsightCandidate]:
        """The minute's most dangerous completed pass, if it is a real line-breaker."""
        last = state.pulse.counter.window(minute, 1)
        kind: InsightKind = "most_dangerous_pass"
        for side in sorted(("home", "away"), key=lambda s: -_team(last, s).best_pass_xt):
            team = _team(last, side)
            if team.best_pass_xt < DANGEROUS_PASS_XT or team.best_pass_id is None:
                continue
            ev = state.events.get(team.best_pass_id)
            if ev is None or damage.packing(ev) < DANGEROUS_PASS_PACKING:
                continue
            if minute - self._last.get((kind, side), -99) < COOLDOWN_MIN[kind]:
                continue
            self._last[(kind, side)] = minute
            self._last_any = minute
            return [
                InsightCandidate(
                    id=self._new_id(),
                    kind=kind,
                    minute=minute,
                    t=min(ev.t + 1.0, now_t),
                    significance=SIGNIFICANCE[kind],
                    side=side,
                    player_id=ev.player_id,
                    event_id=ev.id,
                    evidence=[ev.id],
                )
            ]
        return []

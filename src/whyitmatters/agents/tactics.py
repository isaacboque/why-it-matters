"""Tactical insight detectors, run on every closed minute of the Match Pulse.

Each looks at the latest 5-minute window against the 5 minutes before it and fires only on a
clear, one-sided swing (so it adds a reason rather than repeating "chaos"):

- press_surge:      a team wins the ball high up the pitch and squeezes its opponent's build-up
- midfield_battle:  a team wins most of the midfield duels (over a real sample)
- danger_turnovers: a team keeps losing the ball in its own half, far more than the other
- direct_switch:    a team starts going long while the other side presses it

Thresholds were set on seeds 0-39; the held-out check is the insight-per-match table in README.
"""

from __future__ import annotations

from collections.abc import Callable

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.models import InsightCandidate, InsightKind
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

COOLDOWN_MIN = {  # the same kind about the same team is not voiced again within this long
    "press_surge": 15,
    "midfield_battle": 20,
    "danger_turnovers": 15,
    "direct_switch": 20,
}
ANY_TACTICAL_GAP_MIN = 6  # and at most one tactical insight every few minutes
AFTER_SHIFT_QUIET_MIN = 4  # a control shift has just said it; do not repeat it as a reason
SIGNIFICANCE = {
    "press_surge": 0.55,
    "midfield_battle": 0.5,
    "danger_turnovers": 0.5,
    "direct_switch": 0.45,
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
        for side in ("home", "away"):
            me, opp, was = _team(now, side), _team(now, _other(side)), _team(before, side)
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
            return [
                InsightCandidate(
                    id=self._new_id(),
                    kind=kind,
                    minute=minute,
                    t=min((minute + 1) * 60.0, now_t),  # the last minute closes at full time
                    significance=SIGNIFICANCE[kind],
                    side=side,
                    window=(now.start_minute, now.end_minute),
                    evidence=_events_in(state, now, pred),
                )
            ]  # one tactical insight per closed minute
        return []

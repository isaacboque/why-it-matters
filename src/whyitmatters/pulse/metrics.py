"""Per-minute counters and rolling-window team metrics.

Definitions (all from the acting team's perspective, attacking left to right):
- possession_share: share of in-play seconds each team had the ball
- field_tilt: a team's share of both teams' passes made in the final third (x >= 70)
- ppda: opponent passes in their own defensive 60% (x <= 63) per defensive action
  (tackle, interception, foul) the team makes in its attacking 60% (x >= 42). Lower = more pressing.
- tempo: passes per minute of possession
- losses: open-play possession losses (tackle won, interception, pass out of play)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from whyitmatters.schema import Event, EventType, Outcome, Side

FINAL_THIRD_X = 70.0
PRESS_ZONE_X = 42.0  # defender's attacking 60%
BUILD_UP_X = 63.0  # attacker's defensive 60%
MAX_INPLAY_GAP = 20.0  # seconds; longer gaps are dead ball and not credited


@dataclass
class SideMinute:
    poss_seconds: float = 0.0
    passes: int = 0
    passes_complete: int = 0
    final_third_passes: int = 0
    build_up_passes: int = 0  # passes in own defensive 60%, faced by opponent's press
    press_actions: int = 0  # defensive actions in the press zone
    pressures: int = 0
    losses: int = 0
    chains: int = 0
    short_chains: int = 0  # possessions with <= 2 passes
    shots: int = 0
    xg: float = 0.0
    goals: int = 0
    evidence: list[str] = field(default_factory=list)  # event ids worth citing


class TeamWindow(BaseModel):
    possession_share: float
    pass_completion: float
    field_tilt: float
    ppda: float | None
    tempo: float
    losses_per_min: float
    short_chain_share: float
    pressures: int
    shots: int
    xg: float
    goals: int


class WindowMetrics(BaseModel):
    start_minute: int
    end_minute: int
    home: TeamWindow
    away: TeamWindow
    turnovers_per_min: float
    evidence: list[str]


class MinuteCounter:
    """Streams events into per-minute buckets for both teams."""

    def __init__(self) -> None:
        self.buckets: dict[int, dict[Side, SideMinute]] = defaultdict(
            lambda: {"home": SideMinute(), "away": SideMinute()}
        )
        self.poss_side: Side | None = None
        self.chain_passes = 0
        self.last_t: float | None = None
        self.last_period: int | None = None
        self.max_minute = 0

    def ingest(self, ev: Event) -> None:
        b = self.buckets[ev.minute]
        self.max_minute = max(self.max_minute, ev.minute)
        other: Side = "away" if ev.side == "home" else "home"

        # Credit in-play time to whoever had the ball since the previous event
        if self.last_t is not None and self.last_period == ev.period and self.poss_side:
            gap = ev.t - self.last_t
            if 0 < gap <= MAX_INPLAY_GAP:
                b[self.poss_side].poss_seconds += gap
        self.last_t, self.last_period = ev.t, ev.period

        s = b[ev.side]
        if ev.type == EventType.KICK_OFF:
            self._close_chain(b, turnover=False)
            self.poss_side = ev.side
        elif ev.type in (EventType.PASS, EventType.CARRY):
            if self.poss_side != ev.side:
                self._close_chain(b, turnover=False)
                self.poss_side = ev.side
            if ev.type == EventType.PASS:
                s.passes += 1
                self.chain_passes += 1
                if ev.outcome == Outcome.COMPLETE:
                    s.passes_complete += 1
                if ev.x >= FINAL_THIRD_X:
                    s.final_third_passes += 1
                if ev.x <= BUILD_UP_X:
                    s.build_up_passes += 1
        elif ev.type == EventType.SHOT:
            s.shots += 1
            s.xg += ev.xg or 0.0
            s.evidence.append(ev.id)
            if ev.outcome == Outcome.GOAL:
                s.goals += 1
            self._close_chain(b, turnover=False)
            self.poss_side = None
        elif ev.type == EventType.PRESSURE:
            s.pressures += 1
        elif ev.type in (EventType.TACKLE, EventType.INTERCEPTION, EventType.FOUL):
            if ev.x >= PRESS_ZONE_X:
                s.press_actions += 1
            won = ev.type == EventType.INTERCEPTION or ev.outcome == Outcome.WON
            if won and ev.type != EventType.FOUL:
                if self.poss_side == other:
                    b[other].losses += 1
                    b[other].evidence.append(ev.id)
                    self._close_chain(b, turnover=True)
                self.poss_side = ev.side
        elif ev.type == EventType.BALL_OUT:
            if self.poss_side == ev.side:
                s.losses += 1
                self._close_chain(b, turnover=True)
            self.poss_side = None
        elif ev.type == EventType.HALF_END:
            self._close_chain(b, turnover=False)
            self.poss_side = None
            self.last_t = None

    def _close_chain(self, b: dict[Side, SideMinute], turnover: bool) -> None:
        if self.poss_side is None:
            self.chain_passes = 0
            return
        side = b[self.poss_side]
        side.chains += 1
        if self.chain_passes <= 2:
            side.short_chains += 1
        self.chain_passes = 0

    def window(self, end_minute: int, size: int) -> WindowMetrics:
        start = max(0, end_minute - size + 1)
        agg: dict[Side, SideMinute] = {"home": SideMinute(), "away": SideMinute()}
        evidence: list[str] = []
        for m in range(start, end_minute + 1):
            if m not in self.buckets:
                continue
            for side in ("home", "away"):
                src, dst = self.buckets[m][side], agg[side]
                for f in (
                    "poss_seconds", "passes", "passes_complete", "final_third_passes",
                    "build_up_passes", "press_actions", "pressures", "losses", "chains",
                    "short_chains", "shots", "xg", "goals",
                ):
                    setattr(dst, f, getattr(dst, f) + getattr(src, f))
                evidence.extend(src.evidence)
        minutes = end_minute - start + 1
        h, a = agg["home"], agg["away"]
        total_poss = h.poss_seconds + a.poss_seconds or 1.0
        total_ft = h.final_third_passes + a.final_third_passes

        def team(me: SideMinute, opp: SideMinute) -> TeamWindow:
            poss_min = me.poss_seconds / 60.0
            return TeamWindow(
                possession_share=round(me.poss_seconds / total_poss, 3),
                pass_completion=round(me.passes_complete / me.passes, 3) if me.passes else 0.0,
                field_tilt=round(me.final_third_passes / total_ft, 3) if total_ft else 0.5,
                ppda=round(opp.build_up_passes / me.press_actions, 1) if me.press_actions else None,
                tempo=round(me.passes / poss_min, 1) if poss_min > 0.1 else 0.0,
                losses_per_min=round(me.losses / minutes, 2),
                short_chain_share=round(me.short_chains / me.chains, 3) if me.chains else 0.0,
                pressures=me.pressures,
                shots=me.shots,
                xg=round(me.xg, 2),
                goals=me.goals,
            )

        return WindowMetrics(
            start_minute=start,
            end_minute=end_minute,
            home=team(h, a),
            away=team(a, h),
            turnovers_per_min=round((h.losses + a.losses) / minutes, 2),
            evidence=evidence[-12:],
        )

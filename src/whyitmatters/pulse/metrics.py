"""Per-minute counters and rolling-window team metrics.

Definitions (all from the acting team's perspective, attacking left to right):
- possession_share: share of in-play seconds each team had the ball
- field_tilt: a team's share of both teams' passes made in the final third (x >= 70)
- ppda: opponent passes in their own defensive 60% (x <= 63) per defensive action
  (tackle, interception, foul) the team makes in its attacking 60% (x >= 42). Lower = more pressing.
- tempo: passes per minute of possession
- losses: open-play possession losses (tackle won, interception, pass out of play)

Tactical metrics (also from the acting team's perspective; SPEC.md has the one-line versions):
- duels: every tackle (won or lost) and interception; the winner is credited, in their own
  coordinates, to the defensive (x < 35), middle (35 <= x < 70) or attacking (x >= 70) third
- duel_share_<zone>: a team's duels won in a zone / (its wins + the opponent's wins in the same
  physical area, i.e. the mirrored zone). None when nobody won a duel there
- high_recoveries / final_third_recoveries: ball won (tackle won or interception)
  at x >= 52.5 / x >= 70
- counter_press: ball won back within 5 s of the same team losing it
- own_half_losses: possession lost at x < 52.5 (dangerous losses)
- progressive_passes: completed passes that move the ball >= 10 m towards goal
  or into the final third
- long_ball_share: share of a team's passes that travel >= 30 m
- central_buildup_share: share of build-up passes (x <= 63) started in the central
  third of the pitch width
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from whyitmatters.pulse import damage
from whyitmatters.pulse import xt as xt_model
from whyitmatters.pulse.shape import (
    MIN_FRAMES,
    ShapeSummary,
    formation_code,
    own_frame,
    possession_side,
    summarize,
)
from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, Event, EventType, Outcome, Side

FINAL_THIRD_X = 70.0
PRESS_ZONE_X = 42.0  # defender's attacking 60%
BUILD_UP_X = 63.0  # attacker's defensive 60%
MAX_INPLAY_GAP = 20.0  # seconds; longer gaps are dead ball and not credited
HALF_X = PITCH_LENGTH / 2
DEFENSIVE_THIRD_X = 35.0
COUNTER_PRESS_S = 5.0
PROGRESSIVE_M = 10.0
LONG_BALL_M = 30.0
CENTRAL_Y = (PITCH_WIDTH / 3, 2 * PITCH_WIDTH / 3)
ZONES = ("def", "mid", "att")


def zone_of(x: float) -> str:
    """Third of the pitch (in the acting team's coordinates)."""
    return "def" if x < DEFENSIVE_THIRD_X else "mid" if x < FINAL_THIRD_X else "att"


def duel_winner(ev: Event) -> tuple[Side, float] | None:
    """Who won the duel an event records, and where, in the winner's own coordinates.

    A tackle is a duel the tackler either wins or loses (a lost tackle is the ball carrier's
    win, seen from the other end of the pitch); an interception is always a win. Other events
    are not duels.
    """
    if ev.type == EventType.INTERCEPTION or (
        ev.type == EventType.TACKLE and ev.outcome == Outcome.WON
    ):
        return ev.side, ev.x
    if ev.type == EventType.TACKLE:
        return ("away" if ev.side == "home" else "home"), PITCH_LENGTH - ev.x
    return None


def is_recovery(ev: Event) -> bool:
    """The acting team wins the ball: a successful tackle or an interception."""
    return ev.type == EventType.INTERCEPTION or (
        ev.type == EventType.TACKLE and ev.outcome == Outcome.WON
    )


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
    duels_def: int = 0  # duels this team won, by third (own coordinates)
    duels_mid: int = 0
    duels_att: int = 0
    high_recoveries: int = 0
    final_third_recoveries: int = 0
    counter_press: int = 0
    own_half_losses: int = 0
    progressive_passes: int = 0
    long_balls: int = 0
    central_build_up_passes: int = 0
    # Expected Threat added by completed passes and carries (pulse/xt.py)
    xt: float = 0.0
    xt_zone: list[float] = field(default_factory=lambda: [0.0] * xt_model.ZONES18)
    # Positional sums from freeze frames: 11 x (sum x, sum y), in and out of possession
    pos_in: list[float] = field(default_factory=lambda: [0.0] * 22)
    pos_out: list[float] = field(default_factory=lambda: [0.0] * 22)
    n_in: int = 0
    n_out: int = 0
    # Damage (pulse/damage.py): passes that go past opponents, and where the ball arrives
    line_breaks: int = 0
    packing: int = 0
    between_lines: int = 0
    box_entries: int = 0
    zone14_entries: int = 0
    halfspace_entries: int = 0
    best_pass_xt: float = 0.0
    best_pass_id: str | None = None
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
    # tactical metrics (see the module docstring)
    passes: int = 0
    duels_won_def: int = 0
    duels_won_mid: int = 0
    duels_won_att: int = 0
    duel_share_def: float | None = None
    duel_share_mid: float | None = None
    duel_share_att: float | None = None
    high_recoveries: int = 0
    final_third_recoveries: int = 0
    counter_press: int = 0
    own_half_losses: int = 0
    progressive_passes: int = 0
    long_ball_share: float = 0.0
    central_buildup_share: float = 0.0
    # value and shape (freeze frames): see pulse/xt.py and pulse/shape.py
    xt: float = 0.0
    xt_zone: list[float] = []
    formation_out: float | None = None  # formation code, e.g. 442.0 for "4-4-2"
    formation_in: float | None = None
    line_height: float | None = None  # out-of-possession back line, metres from own goal
    line_height_in: float | None = None
    gap_def_mid: float | None = None
    gap_mid_att: float | None = None
    team_length: float | None = None
    team_width: float | None = None
    compactness: float | None = None
    shape_out: ShapeSummary | None = None
    shape_in: ShapeSummary | None = None
    # damage (pulse/damage.py)
    line_breaks: int = 0
    packing: int = 0
    between_lines: int = 0
    box_entries: int = 0
    zone14_entries: int = 0
    halfspace_entries: int = 0
    xt_share_left: float | None = None  # share of the team's positive xT that ended in a lane
    xt_share_centre: float | None = None
    xt_share_right: float | None = None
    best_pass_xt: float = 0.0  # the window's most dangerous completed pass
    best_pass_id: str | None = None


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
        self.last_loss_t: dict[Side, float] = {}  # when each team last lost the ball

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
        if ev.freeze is not None:
            holder = possession_side(ev)
            for side in ("home", "away"):
                frame = own_frame(ev, side)
                if frame is None:
                    continue
                dst = b[side]
                acc = dst.pos_in if side == holder else dst.pos_out
                for i, (px, py) in enumerate(frame):
                    acc[2 * i] += px
                    acc[2 * i + 1] += py
                if side == holder:
                    dst.n_in += 1
                else:
                    dst.n_out += 1
        if (
            ev.type in (EventType.PASS, EventType.CARRY)
            and ev.end_x is not None
            and (ev.type == EventType.CARRY or ev.outcome == Outcome.COMPLETE)
        ):
            added = xt_model.added(ev.x, ev.y, ev.end_x, ev.end_y)
            s.xt += added
            if added > 0:
                s.xt_zone[xt_model.zone18(ev.end_x, ev.end_y)] += added
            box, z14, half = damage.entries(ev)
            s.box_entries += box
            s.zone14_entries += z14
            s.halfspace_entries += half
            if ev.type == EventType.PASS:
                if damage.lines_broken(ev):
                    s.line_breaks += 1
                s.packing += damage.packing(ev)
                s.between_lines += damage.between_lines(ev)
                if added > s.best_pass_xt:
                    s.best_pass_xt, s.best_pass_id = added, ev.id
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
                    if ev.end_x is not None and (
                        ev.end_x - ev.x >= PROGRESSIVE_M or (ev.x < FINAL_THIRD_X <= ev.end_x)
                    ):
                        s.progressive_passes += 1
                if ev.x >= FINAL_THIRD_X:
                    s.final_third_passes += 1
                if ev.x <= BUILD_UP_X:
                    s.build_up_passes += 1
                    if CENTRAL_Y[0] <= ev.y <= CENTRAL_Y[1]:
                        s.central_build_up_passes += 1
                if (ev.pass_distance or 0.0) >= LONG_BALL_M:
                    s.long_balls += 1
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
            duel = duel_winner(ev)
            if duel is not None:
                winner, wx = duel
                setattr(
                    b[winner],
                    f"duels_{zone_of(wx)}",
                    getattr(b[winner], f"duels_{zone_of(wx)}") + 1,
                )
            won = ev.type == EventType.INTERCEPTION or ev.outcome == Outcome.WON
            if won and ev.type != EventType.FOUL:
                if ev.x >= HALF_X:
                    s.high_recoveries += 1
                if ev.x >= FINAL_THIRD_X:
                    s.final_third_recoveries += 1
                lost_at = self.last_loss_t.get(ev.side)
                if lost_at is not None and 0 <= ev.t - lost_at <= COUNTER_PRESS_S:
                    s.counter_press += 1
                if self.poss_side == other:
                    b[other].losses += 1
                    b[other].evidence.append(ev.id)
                    if PITCH_LENGTH - ev.x < HALF_X:
                        b[other].own_half_losses += 1
                    self.last_loss_t[other] = ev.t
                    self._close_chain(b, turnover=True)
                self.poss_side = ev.side
        elif ev.type == EventType.BALL_OUT:
            if self.poss_side == ev.side:
                s.losses += 1
                if ev.x < HALF_X:
                    s.own_half_losses += 1
                self.last_loss_t[ev.side] = ev.t
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
                    "poss_seconds",
                    "passes",
                    "passes_complete",
                    "final_third_passes",
                    "build_up_passes",
                    "press_actions",
                    "pressures",
                    "losses",
                    "chains",
                    "short_chains",
                    "shots",
                    "xg",
                    "goals",
                    "duels_def",
                    "duels_mid",
                    "duels_att",
                    "high_recoveries",
                    "final_third_recoveries",
                    "counter_press",
                    "own_half_losses",
                    "progressive_passes",
                    "long_balls",
                    "central_build_up_passes",
                    "xt",
                    "n_in",
                    "n_out",
                    "line_breaks",
                    "packing",
                    "between_lines",
                    "box_entries",
                    "zone14_entries",
                    "halfspace_entries",
                ):
                    setattr(dst, f, getattr(dst, f) + getattr(src, f))
                if src.best_pass_xt > dst.best_pass_xt:
                    dst.best_pass_xt, dst.best_pass_id = src.best_pass_xt, src.best_pass_id
                for f in ("pos_in", "pos_out", "xt_zone"):
                    a, b2 = getattr(dst, f), getattr(src, f)
                    for i, v in enumerate(b2):
                        a[i] += v
                evidence.extend(src.evidence)
        minutes = end_minute - start + 1
        h, a = agg["home"], agg["away"]
        total_poss = h.poss_seconds + a.poss_seconds or 1.0
        total_ft = h.final_third_passes + a.final_third_passes

        def duel_share(mine: int, theirs_mirrored: int) -> float | None:
            total = mine + theirs_mirrored
            return round(mine / total, 3) if total else None

        def shape(sums: list[float], n: int) -> ShapeSummary | None:
            if n < MIN_FRAMES:
                return None
            return summarize([(sums[2 * i] / n, sums[2 * i + 1] / n) for i in range(11)])

        def team(me: SideMinute, opp: SideMinute) -> TeamWindow:
            poss_min = me.poss_seconds / 60.0
            out, inn = shape(me.pos_out, me.n_out), shape(me.pos_in, me.n_in)
            lanes = [sum(me.xt_zone[i * 3 + j] for i in range(6)) for j in range(3)]
            positive = sum(lanes)

            def lane_share(j: int) -> float | None:
                return round(lanes[j] / positive, 3) if positive > 0 else None

            return TeamWindow(
                line_breaks=me.line_breaks,
                packing=me.packing,
                between_lines=me.between_lines,
                box_entries=me.box_entries,
                zone14_entries=me.zone14_entries,
                halfspace_entries=me.halfspace_entries,
                xt_share_left=lane_share(0),
                xt_share_centre=lane_share(1),
                xt_share_right=lane_share(2),
                best_pass_xt=round(me.best_pass_xt, 3),
                best_pass_id=me.best_pass_id,
                xt=round(me.xt, 3),
                xt_zone=[round(v, 3) for v in me.xt_zone],
                formation_out=formation_code(out.formation) if out else None,
                formation_in=formation_code(inn.formation) if inn else None,
                line_height=out.line_height if out else None,
                line_height_in=inn.line_height if inn else None,
                gap_def_mid=out.gap_def_mid if out else None,
                gap_mid_att=out.gap_mid_att if out else None,
                team_length=out.length if out else None,
                team_width=out.width if out else None,
                compactness=out.compactness if out else None,
                shape_out=out,
                shape_in=inn,
                passes=me.passes,
                duels_won_def=me.duels_def,
                duels_won_mid=me.duels_mid,
                duels_won_att=me.duels_att,
                # the opponent's wins in the mirrored third are the same patch of grass
                duel_share_def=duel_share(me.duels_def, opp.duels_att),
                duel_share_mid=duel_share(me.duels_mid, opp.duels_mid),
                duel_share_att=duel_share(me.duels_att, opp.duels_def),
                high_recoveries=me.high_recoveries,
                final_third_recoveries=me.final_third_recoveries,
                counter_press=me.counter_press,
                own_half_losses=me.own_half_losses,
                progressive_passes=me.progressive_passes,
                long_ball_share=round(me.long_balls / me.passes, 3) if me.passes else 0.0,
                central_buildup_share=(
                    round(me.central_build_up_passes / me.build_up_passes, 3)
                    if me.build_up_passes
                    else 0.0
                ),
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

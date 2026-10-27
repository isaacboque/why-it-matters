"""Seeded, football-realistic match simulator.

The simulator plays possessions action by action. Team behaviour comes from the scripted
phases (see phases.py), so every match carries known answers for evaluation: which team
was in control when, and which moments mattered.

Clock: first half runs 0-45:00 with no added time; the second half runs 45:00-90:00 plus
1-5 minutes of added time. `t` is therefore monotonic across the match.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from whyitmatters.schema import (
    PITCH_LENGTH,
    PITCH_WIDTH,
    Event,
    EventType,
    GroundTruth,
    KeyMoment,
    Match,
    MatchMeta,
    Outcome,
    Player,
    Side,
    Team,
)
from whyitmatters.simulator.phases import Style, script_phases, style_at
from whyitmatters.simulator.positions import add_freeze_frames
from whyitmatters.simulator.teams import CLUBS, VENUES, make_team, nominal_xy
from whyitmatters.simulator.xg import expected_goals

HALF = 45 * 60
BIG_CHANCE_XG = 0.3
# Final-third shot rate, set with xg.XG_SCALE so shots and goals per team match the Premier League
# (docs/STATS-AUDIT.md)
SHOT_RATE = 1.35


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


def _flip(x: float, y: float) -> tuple[float, float]:
    """Convert a location into the other team's attacking perspective."""
    return PITCH_LENGTH - x, PITCH_WIDTH - y


def _clip(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass
class _State:
    t: float = 0.0
    period: int = 1
    seq: int = 0
    possession_id: int = 0
    score: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})


class Simulator:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)
        clubs = self.rng.sample(CLUBS, 2)
        self.teams: dict[Side, Team] = {
            "home": make_team(self.rng, clubs[0], "home"),
            "away": make_team(self.rng, clubs[1], "away"),
        }
        # Small fixed quality edge so the same phase never plays out identically
        self.quality: dict[Side, float] = {
            "home": self.rng.uniform(-0.02, 0.03),
            "away": self.rng.uniform(-0.03, 0.02),
        }
        self.phases = script_phases(self.rng)
        self.match_id = (
            f"syn-{seed:04d}-{self.teams['home'].short_name}-{self.teams['away'].short_name}"
        ).lower()
        self.events: list[Event] = []
        self.key_moments: list[KeyMoment] = []
        self.s = _State()

    # ------------------------------------------------------------------ helpers
    def _style(self, side: Side) -> Style:
        return style_at(self.phases, self.s.t / 60.0, side, self.quality[side])

    def _pick_player(self, side: Side, x: float, y: float, exclude: str | None = None) -> Player:
        """A player whose nominal position is near (x, y), in that team's perspective."""
        weights = []
        players = self.teams[side].players
        for p in players:
            nx, ny = nominal_xy(p)
            d = math.hypot(nx - x, (ny - y) * 0.6)
            w = math.exp(-d / 14.0)
            if p.position == "GK" and x > 18:
                w *= 0.02
            if p.id == exclude:
                w = 0.0
            weights.append(w)
        return self.rng.choices(players, weights=weights, k=1)[0]

    def _emit(self, **kw) -> Event:
        s = self.s
        s.seq += 1
        # The last possession of the first half can run a few seconds past 45:00 (a goal also
        # adds a kick-off delay). The clock must not: the second half restarts at 45:00, so
        # those events are stamped at the whistle instead of going back in time.
        # The minute is read from the rounded stamp, so t=60.0 is never "minute 0".
        t = round(min(s.t, HALF - 0.1) if s.period == 1 else s.t, 1)
        ev = Event(
            id=f"{self.match_id}-{s.seq:05d}",
            seq=s.seq,
            t=t,
            period=s.period,
            minute=int(t // 60),
            possession_id=s.possession_id,
            score_home=s.score["home"],
            score_away=s.score["away"],
            **kw,
        )
        self.events.append(ev)
        return ev

    # ------------------------------------------------------------------ match flow
    def run(self) -> Match:
        first: Side = self.rng.choice(["home", "away"])
        self._play_period(1, 0.0, HALF, first)
        added = self.rng.uniform(60, 300)
        self._play_period(2, HALF, 2 * HALF + added, _other(first))
        meta = MatchMeta(
            match_id=self.match_id,
            seed=self.seed,
            venue=self.rng.choice(VENUES),
            kickoff_local=f"2026-{self.rng.randint(8, 12):02d}-{self.rng.randint(1, 28):02d}T15:00",
            home=self.teams["home"],
            away=self.teams["away"],
        )
        shapes = add_freeze_frames(self.events, self.teams, self.phases, self.seed)
        truth = GroundTruth(phases=self.phases, key_moments=self.key_moments, shapes=shapes)
        return Match(meta=meta, events=self.events, truth=truth)

    def _play_period(self, period: int, start: float, end: float, kick_off: Side) -> None:
        s = self.s
        s.period = period
        s.t = start
        side, x, y = self._kick_off(kick_off)
        while s.t < end:
            side, x, y = self._possession(side, x, y, end)
        self._emit(type=EventType.HALF_END, side=side, x=52.5, y=34.0)

    def _kick_off(self, side: Side) -> tuple[Side, float, float]:
        self.s.possession_id += 1
        striker = next(p for p in self.teams[side].players if p.position == "ST")
        self._emit(type=EventType.KICK_OFF, side=side, player_id=striker.id, x=52.5, y=34.0)
        self.s.t += 1.0
        return side, 48.0, 34.0

    # ------------------------------------------------------------------ possession
    def _possession(self, att: Side, x: float, y: float, end: float) -> tuple[Side, float, float]:
        """Play one possession; return who has the ball next and where (their perspective)."""
        s = self.s
        rng = self.rng
        dfn = _other(att)
        s.possession_id += 1
        holder = self._pick_player(att, x, y)

        while s.t < end:
            sa, sd = self._style(att), self._style(dfn)

            # 1. Defensive pressure on the ball
            high = 1.0 if x < 52.5 else 0.55
            pressured = rng.random() < 0.10 + 0.55 * sd.press * high
            if pressured:
                dx_, dy_ = _flip(x, y)
                presser = self._pick_player(dfn, dx_, dy_)
                self._emit(
                    type=EventType.PRESSURE, side=dfn, player_id=presser.id,
                    x=round(dx_, 1), y=round(dy_, 1),
                )
                # 2. Tackle attempt or foul
                if rng.random() < 0.10 + 0.22 * sd.press:
                    won = rng.random() < 0.55
                    if rng.random() < 0.12:
                        self._emit(
                            type=EventType.FOUL, side=dfn, player_id=presser.id,
                            x=round(dx_, 1), y=round(dy_, 1),
                        )
                        s.t += rng.uniform(12, 30)
                        continue
                    self._emit(
                        type=EventType.TACKLE, side=dfn, player_id=presser.id,
                        x=round(dx_, 1), y=round(dy_, 1),
                        outcome=Outcome.WON if won else Outcome.LOST,
                    )
                    s.t += rng.uniform(1.0, 2.5)
                    if won:
                        return dfn, dx_, dy_

            # 3. Shot?
            if x > 75:
                central = 1.0 - abs(y - PITCH_WIDTH / 2) / (PITCH_WIDTH / 2)
                p_shot = SHOT_RATE * (0.012 + 0.19 * ((x - 75) / 30) ** 1.5 * max(central, 0.15))
                if rng.random() < p_shot:
                    return self._shot(att, holder, x, y, pressured)

            # 4. Pass
            if rng.random() < 0.17 * sa.directness and x < 70:
                dx = rng.gauss(36, 8)
            else:
                dx = rng.gauss(6.5 * sa.directness, 7.5)
            if x > 88:
                dx = min(dx, rng.uniform(-6, 6))
            end_x = _clip(x + dx, 1.0, 104.0)
            end_y = _clip(y + rng.gauss(0, 14), 1.0, 67.0)
            dist = math.hypot(end_x - x, end_y - y)
            difficulty = _clip(
                0.12 + dist / 55 + (0.22 if pressured else 0.0) + max(0.0, end_x - 70) / 35 * 0.3,
                0.0, 1.0,
            )
            p_ok = _clip(sa.skill + 0.15 - 0.35 * difficulty, 0.25, 0.98)
            ok = rng.random() < p_ok
            speed = _clip(28 + dist * 1.4 + rng.gauss(0, 6), 18, 115)
            receiver = self._pick_player(att, end_x, end_y, exclude=holder.id)
            self._emit(
                type=EventType.PASS, side=att, player_id=holder.id,
                x=round(x, 1), y=round(y, 1), end_x=round(end_x, 1), end_y=round(end_y, 1),
                outcome=Outcome.COMPLETE if ok else Outcome.INCOMPLETE,
                receiver_id=receiver.id if ok else None,
                under_pressure=pressured,
                pass_distance=round(dist, 1), pass_difficulty=round(difficulty, 2),
                ball_speed_kmh=round(speed, 1),
            )
            s.t += (0.8 + dist / (speed / 3.6) + rng.uniform(1.6, 4.4)) * sa.tempo

            if not ok:
                if rng.random() < 0.72:
                    ix, iy = _flip(end_x, end_y)
                    interceptor = self._pick_player(dfn, ix, iy)
                    self._emit(
                        type=EventType.INTERCEPTION, side=dfn, player_id=interceptor.id,
                        x=round(ix, 1), y=round(iy, 1), outcome=Outcome.WON,
                    )
                    s.t += rng.uniform(0.5, 1.5)
                    return dfn, ix, iy
                self._emit(type=EventType.BALL_OUT, side=att, x=round(end_x, 1), y=round(end_y, 1))
                s.t += rng.uniform(6, 16)
                rx, ry = _flip(end_x, end_y)
                if end_x > 100:
                    return dfn, 6.0, 34.0  # goal kick
                return dfn, rx, 1.0 if ry < 34 else 67.0  # throw-in

            x, y, holder = end_x, end_y, receiver

            # 5. Carry
            if rng.random() < 0.32:
                cx = _clip(x + abs(rng.gauss(4.5, 4)) * min(sa.directness, 1.4), 1.0, 104.0)
                cy = _clip(y + rng.gauss(0, 4), 1.0, 67.0)
                cdist = math.hypot(cx - x, cy - y)
                carry_secs = max(cdist / rng.uniform(4.0, 7.5), 0.6)
                self._emit(
                    type=EventType.CARRY, side=att, player_id=holder.id,
                    x=round(x, 1), y=round(y, 1), end_x=round(cx, 1), end_y=round(cy, 1),
                    ball_speed_kmh=round(cdist / carry_secs * 3.6, 1),
                )
                s.t += carry_secs * sa.tempo
                x, y = cx, cy

        return att, x, y

    def _shot(
        self, att: Side, shooter: Player, x: float, y: float, pressured: bool
    ) -> tuple[Side, float, float]:
        s, rng = self.s, self.rng
        dfn = _other(att)
        xg = expected_goals(x, y, pressured)
        r = rng.random()
        r2 = rng.random()
        if r < xg:
            outcome = Outcome.GOAL
        elif r2 < 0.27:
            outcome = Outcome.BLOCKED
        elif r2 < 0.52:
            outcome = Outcome.SAVED
        else:
            outcome = Outcome.OFF_TARGET
        if outcome == Outcome.GOAL:
            s.score[att] += 1
        ev = self._emit(
            type=EventType.SHOT, side=att, player_id=shooter.id,
            x=round(x, 1), y=round(y, 1), end_x=105.0, end_y=round(34 + rng.gauss(0, 3), 1),
            outcome=outcome, under_pressure=pressured, xg=xg,
            ball_speed_kmh=round(_clip(rng.gauss(88, 14), 45, 130), 1),
        )
        if outcome == Outcome.GOAL or xg >= BIG_CHANCE_XG:
            self.key_moments.append(
                KeyMoment(
                    kind="goal" if outcome == Outcome.GOAL else "big_chance",
                    event_id=ev.id, minute=ev.minute, side=att, xg=xg,
                )
            )
        if outcome == Outcome.GOAL:
            s.t += rng.uniform(45, 75)
            side, nx, ny = self._kick_off(dfn)
            return side, nx, ny
        if outcome == Outcome.SAVED:
            s.t += rng.uniform(3, 8)
            return dfn, 8.0, 34.0
        if outcome == Outcome.OFF_TARGET:
            s.t += rng.uniform(15, 30)
            return dfn, 6.0, 34.0
        s.t += rng.uniform(1, 3)  # blocked: loose ball
        if rng.random() < 0.5:
            return att, max(x - 10, 60.0), y
        bx, by = _flip(x, y)
        return dfn, bx + 4, by


def simulate(seed: int) -> Match:
    return Simulator(seed).run()

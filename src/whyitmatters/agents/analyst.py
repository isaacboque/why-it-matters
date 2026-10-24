"""Analyst: decides what is worth saying. Turns the stream into ranked insight candidates."""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.models import InsightCandidate
from whyitmatters.pulse import Transition
from whyitmatters.pulse.engine import PulseOutput
from whyitmatters.schema import Event, EventType, Outcome

BIG_CHANCE_XG = 0.3
PASS_MASTER_MIN = 40  # completed passes
PASS_MASTER_LEAD = 10  # ... and this many more than the next best passer
PASS_MASTER_STEP = 40  # the same player is only mentioned again after this many more
TOP_SPEED_FLOOR_KMH = 24.0
TOP_SPEED_MIN_GAP_MIN = 10
SHIFT_FLICKER_MIN = 4  # a non-control shift this soon after another one is noise
SHIFT_REPEAT_MIN = {  # the same kind of shift is not voiced again within this many minutes
    "home_control": 10,
    "away_control": 10,
    "chaos": 15,
    "balanced": 12,
}

SIGNIFICANCE = {
    "goal": 1.0,
    "state_shift": 0.8,
    "big_chance": 0.6,
    "top_speed": 0.35,
    "pass_master": 0.3,
}


class Analyst:
    name = "analyst"

    def __init__(self) -> None:
        self._n = 0
        self._top_speed = TOP_SPEED_FLOOR_KMH
        self._last_speed_minute = -TOP_SPEED_MIN_GAP_MIN
        self._last_shift: dict[str, int] = {}  # to_state -> minute of the last one voiced
        self._last_transition_minute = -SHIFT_FLICKER_MIN
        self._voiced_state: str | None = None  # the state the audience was last told about
        self._last_master: tuple[str, int] | None = None  # (player, completed passes)

    def _id(self) -> str:
        self._n += 1
        return f"in-{self._n:03d}"

    def _worth_saying(self, tr: Transition) -> bool:
        """Drop shifts a pundit would not mention: flicker, repeats, and 'settled' after chaos."""
        flicker = tr.detected_minute - self._last_transition_minute < SHIFT_FLICKER_MIN
        self._last_transition_minute = tr.detected_minute
        if tr.to_state != "home_control" and tr.to_state != "away_control":
            if flicker:
                return False
            if tr.to_state == "balanced" and tr.from_state == "chaos":
                return False
        if tr.to_state == self._voiced_state:
            return False  # the audience was already told the game is in this state
        last = self._last_shift.get(tr.to_state)
        if last is not None and tr.detected_minute - last < SHIFT_REPEAT_MIN[tr.to_state]:
            return False
        self._last_shift[tr.to_state] = tr.detected_minute
        self._voiced_state = tr.to_state
        return True

    def run(
        self, state: Blackboard, ev: Event, pulse_out: list[PulseOutput]
    ) -> list[InsightCandidate]:
        out: list[InsightCandidate] = []

        for item in pulse_out:
            if isinstance(item, Transition) and self._worth_saying(item):
                sig = SIGNIFICANCE["state_shift"]
                if item.to_state == "balanced":
                    sig = 0.5
                elif item.to_state == "chaos":
                    sig = 0.75
                side = {"home_control": "home", "away_control": "away"}.get(item.to_state)
                out.append(
                    InsightCandidate(
                        id=self._id(),
                        kind="state_shift",
                        minute=item.detected_minute,
                        t=(item.detected_minute + 1) * 60.0,
                        significance=sig,
                        side=side,
                        transition_id=item.id,
                        to_state=item.to_state,
                        from_state=item.from_state,
                        evidence=item.evidence,
                    )
                )

        if ev.type == EventType.SHOT and ev.xg is not None:
            if ev.outcome == Outcome.GOAL:
                out.append(
                    InsightCandidate(
                        id=self._id(),
                        kind="goal",
                        minute=ev.minute,
                        t=ev.t,
                        significance=SIGNIFICANCE["goal"],
                        side=ev.side,
                        player_id=ev.player_id,
                        event_id=ev.id,
                        evidence=[ev.id],
                    )
                )
            elif ev.xg >= BIG_CHANCE_XG:
                out.append(
                    InsightCandidate(
                        id=self._id(),
                        kind="big_chance",
                        minute=ev.minute,
                        t=ev.t,
                        significance=min(1.0, SIGNIFICANCE["big_chance"] + (ev.xg - 0.3) * 0.5),
                        side=ev.side,
                        player_id=ev.player_id,
                        event_id=ev.id,
                        evidence=[ev.id],
                    )
                )

        elif (
            ev.type == EventType.CARRY
            and ev.ball_speed_kmh
            and ev.minute >= 5
            and ev.ball_speed_kmh >= self._top_speed + 0.5
        ):
            self._top_speed = ev.ball_speed_kmh
            if ev.minute - self._last_speed_minute >= TOP_SPEED_MIN_GAP_MIN:
                self._last_speed_minute = ev.minute
                out.append(
                    InsightCandidate(
                        id=self._id(),
                        kind="top_speed",
                        minute=ev.minute,
                        t=ev.t,
                        significance=SIGNIFICANCE["top_speed"],
                        side=ev.side,
                        player_id=ev.player_id,
                        event_id=ev.id,
                        evidence=[ev.id],
                    )
                )

        elif ev.type == EventType.PASS and ev.outcome == Outcome.COMPLETE and ev.player_id:
            done = state.stats[ev.player_id].completed
            best_other = max(
                (st.completed for pid, st in state.stats.items() if pid != ev.player_id),
                default=0,
            )
            repeat = self._last_master is not None and self._last_master[0] == ev.player_id
            fresh = not repeat or done >= self._last_master[1] + PASS_MASTER_STEP
            if done >= PASS_MASTER_MIN and done >= best_other + PASS_MASTER_LEAD and fresh:
                self._last_master = (ev.player_id, done)
                out.append(
                    InsightCandidate(
                        id=self._id(),
                        kind="pass_master",
                        minute=ev.minute,
                        t=ev.t,
                        significance=SIGNIFICANCE["pass_master"],
                        side=ev.side,
                        player_id=ev.player_id,
                        event_id=ev.id,
                        evidence=[ev.id],
                    )
                )
        return out

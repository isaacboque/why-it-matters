"""Analyst: decides what is worth saying. Turns the stream into ranked insight candidates."""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.models import InsightCandidate
from whyitmatters.pulse import Transition
from whyitmatters.pulse.engine import PulseOutput
from whyitmatters.schema import Event, EventType, Outcome

BIG_CHANCE_XG = 0.3
PASS_MILESTONES = (40, 60, 80)  # only for the match's leading passer
TOP_SPEED_FLOOR_KMH = 24.0
TOP_SPEED_MIN_GAP_MIN = 10

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

    def _id(self) -> str:
        self._n += 1
        return f"in-{self._n:03d}"

    def run(
        self, state: Blackboard, ev: Event, pulse_out: list[PulseOutput]
    ) -> list[InsightCandidate]:
        out: list[InsightCandidate] = []

        for item in pulse_out:
            if isinstance(item, Transition):
                sig = SIGNIFICANCE["state_shift"]
                if item.to_state == "balanced":
                    sig = 0.5
                elif item.to_state == "chaos":
                    sig = 0.75
                side = {"home_control": "home", "away_control": "away"}.get(item.to_state)
                out.append(InsightCandidate(
                    id=self._id(), kind="state_shift", minute=item.detected_minute,
                    t=(item.detected_minute + 1) * 60.0, significance=sig, side=side,
                    transition_id=item.id, to_state=item.to_state, from_state=item.from_state,
                    evidence=item.evidence,
                ))

        if ev.type == EventType.SHOT and ev.xg is not None:
            if ev.outcome == Outcome.GOAL:
                out.append(InsightCandidate(
                    id=self._id(), kind="goal", minute=ev.minute, t=ev.t,
                    significance=SIGNIFICANCE["goal"], side=ev.side, player_id=ev.player_id,
                    event_id=ev.id, evidence=[ev.id],
                ))
            elif ev.xg >= BIG_CHANCE_XG:
                out.append(InsightCandidate(
                    id=self._id(), kind="big_chance", minute=ev.minute, t=ev.t,
                    significance=min(1.0, SIGNIFICANCE["big_chance"] + (ev.xg - 0.3) * 0.5),
                    side=ev.side, player_id=ev.player_id, event_id=ev.id, evidence=[ev.id],
                ))

        elif (
            ev.type == EventType.CARRY
            and ev.ball_speed_kmh
            and ev.minute >= 5
            and ev.ball_speed_kmh >= self._top_speed + 0.5
        ):
            self._top_speed = ev.ball_speed_kmh
            if ev.minute - self._last_speed_minute >= TOP_SPEED_MIN_GAP_MIN:
                self._last_speed_minute = ev.minute
                out.append(InsightCandidate(
                    id=self._id(), kind="top_speed", minute=ev.minute, t=ev.t,
                    significance=SIGNIFICANCE["top_speed"], side=ev.side,
                    player_id=ev.player_id, event_id=ev.id, evidence=[ev.id],
                ))

        elif ev.type == EventType.PASS and ev.outcome == Outcome.COMPLETE and ev.player_id:
            done = state.stats[ev.player_id].completed
            leader = max(state.stats.values(), key=lambda st: st.completed).completed
            if done in PASS_MILESTONES and done >= leader:
                out.append(InsightCandidate(
                    id=self._id(), kind="pass_master", minute=ev.minute, t=ev.t,
                    significance=SIGNIFICANCE["pass_master"] + 0.05 * PASS_MILESTONES.index(done),
                    side=ev.side, player_id=ev.player_id, event_id=ev.id, evidence=[ev.id],
                ))
        return out

"""Shared match state every agent reads. Fed only by the live event stream.

The Blackboard never sees the simulator's ground truth. Its numbers are recomputed from
raw events, so the Verifier checks claims against an independent source, not against the
copy the Explainer used.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from whyitmatters.pulse import MatchPulse, PulseSnapshot, Transition
from whyitmatters.pulse.engine import PulseOutput
from whyitmatters.schema import Event, EventType, MatchMeta, Outcome, Player, Side


@dataclass
class PlayerStats:
    passes: int = 0
    completed: int = 0
    shots: int = 0
    xg: float = 0.0
    goals: int = 0
    top_carry_kmh: float = 0.0
    completed_at: dict[str, int] = field(default_factory=dict)  # event id -> completed count


class Blackboard:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.pulse = MatchPulse(meta)
        self.players: dict[str, Player] = {
            p.id: p for team in (meta.home, meta.away) for p in team.players
        }
        self.stats: dict[str, PlayerStats] = {pid: PlayerStats() for pid in self.players}
        self.events: dict[str, Event] = {}
        self.team_xg: dict[Side, float] = {"home": 0.0, "away": 0.0}
        self.team_xg_at: dict[str, dict[Side, float]] = {}
        self.score: dict[Side, int] = {"home": 0, "away": 0}
        self.top_carry_kmh = 0.0
        self.last_event: Event | None = None

    # ------------------------------------------------------------------ ingest
    def ingest(self, ev: Event) -> list[PulseOutput]:
        self.events[ev.id] = ev
        self.last_event = ev
        st = self.stats.get(ev.player_id or "")
        if ev.type == EventType.PASS and st is not None:
            st.passes += 1
            if ev.outcome == Outcome.COMPLETE:
                st.completed += 1
                st.completed_at[ev.id] = st.completed
        elif ev.type == EventType.SHOT:
            self.team_xg[ev.side] += ev.xg or 0.0
            self.team_xg_at[ev.id] = dict(self.team_xg)
            if st is not None:
                st.shots += 1
                st.xg += ev.xg or 0.0
            if ev.outcome == Outcome.GOAL:
                self.score[ev.side] += 1
                if st is not None:
                    st.goals += 1
        elif ev.type == EventType.CARRY and st is not None and ev.ball_speed_kmh:
            st.top_carry_kmh = max(st.top_carry_kmh, ev.ball_speed_kmh)
        return self.pulse.ingest(ev)

    def finish(self) -> list[PulseOutput]:
        return self.pulse.finish()

    # ------------------------------------------------------------------ reads
    @property
    def transitions(self) -> list[Transition]:
        return self.pulse.transitions

    @property
    def snapshots(self) -> list[PulseSnapshot]:
        return self.pulse.snapshots

    def team_name(self, side: Side, short: bool = False) -> str:
        team = self.meta.home if side == "home" else self.meta.away
        return team.short_name if short else team.name

    def player_name(self, player_id: str | None) -> str:
        if not player_id or player_id not in self.players:
            return ""
        return self.players[player_id].name

    def side_of(self, player_id: str) -> Side:
        return self.players[player_id].side

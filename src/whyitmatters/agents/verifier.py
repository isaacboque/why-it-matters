"""Verifier: checks every claim against the Blackboard, and every number in the text
against the claims. Nothing reaches air unless both checks pass.
"""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.generator import fmt, numbers_in
from whyitmatters.agents.guardrails import brief_names, known_names, name_violations
from whyitmatters.agents.models import (
    TEAM_WINDOW_METRICS,
    Claim,
    ClaimCheck,
    Draft,
    Lang,
    Verdict,
)
from whyitmatters.pulse import damage
from whyitmatters.pulse import xt as xt_model
from whyitmatters.pulse.buildup import analyse_buildup
from whyitmatters.pulse.metrics import MinuteCounter
from whyitmatters.schema import EventType

# Absolute slack on top of a claim's own tolerance, for float noise only
EPS = 1e-6


class Verifier:
    name = "verifier"

    def __init__(self) -> None:
        self._replays: dict[tuple[int, int], MinuteCounter] = {}

    def _counter(self, state: Blackboard, end: int) -> MinuteCounter:
        """A fresh counter fed from the raw log up to minute `end`.

        Deliberately not `state.pulse.counter`: the Explainer's numbers come from there, so
        reusing it would let a corrupted counter vouch for itself. The metric definitions are
        shared (they are the product's definitions); the accumulation is independent.
        """
        key = (end, len(state.log))
        counter = self._replays.get(key)
        if counter is None:
            if len(self._replays) > 256:
                self._replays.clear()
            counter = MinuteCounter()
            for ev in state.log:
                if ev.minute <= end:
                    counter.ingest(ev)
            self._replays[key] = counter
        return counter

    def resolve(self, state: Blackboard, c: Claim) -> float | None:
        """The true value of a claim, recomputed from the raw event stream."""
        if c.metric in TEAM_WINDOW_METRICS or c.metric == "turnovers_per_min":
            if c.window is None:
                return None
            start, end = c.window
            w = self._counter(state, end).window(end, end - start + 1)
            if c.metric == "turnovers_per_min":
                return w.turnovers_per_min
            if c.side is None:
                return None
            team = w.home if c.side == "home" else w.away
            value = getattr(team, c.metric)
            return None if value is None else float(value)
        if c.metric == "window_minutes":
            return float(c.window[1] - c.window[0] + 1) if c.window else None
        if c.metric == "team_xg":
            if c.side is None:
                return None
            if c.event_id:
                at = state.team_xg_at.get(c.event_id)
                return at[c.side] if at else None
            return state.team_xg[c.side]
        ev = state.events.get(c.event_id or "")
        if ev is None:
            return None
        if c.metric == "shot_xg":
            return ev.xg
        if c.metric == "score_home":
            return float(ev.score_home)
        if c.metric == "score_away":
            return float(ev.score_away)
        if c.metric in ("carry_speed_kmh", "shot_speed_kmh"):
            return ev.ball_speed_kmh
        if c.metric in ("pass_xt_added", "pass_packing"):
            if not damage.is_completed_pass(ev):
                return None
            if c.metric == "pass_packing":
                return float(damage.packing(ev))
            return xt_model.added(ev.x, ev.y, ev.end_x, ev.end_y)
        if c.metric == "pass_difficulty":
            return ev.pass_difficulty
        if c.metric in ("buildup_seconds", "counter_press_in_move", "long_balls_in_move"):
            if ev.type != EventType.SHOT:
                return None
            move = analyse_buildup(state.log, ev)
            if c.metric == "long_balls_in_move":
                return float(move.long_balls)
            if c.metric == "counter_press_in_move":
                return float(move.counter_press)
            return move.seconds
        if c.metric == "player_completed_passes":
            st = state.stats.get(c.player_id or "")
            return float(st.completed_at[ev.id]) if st and ev.id in st.completed_at else None
        return None

    def check_claims(self, state: Blackboard, claims: list[Claim]) -> list[ClaimCheck]:
        checks = []
        for c in claims:
            actual = self.resolve(state, c)
            if actual is None:
                checks.append(
                    ClaimCheck(
                        claim=c,
                        actual=None,
                        ok=False,
                        reason=f"{c.metric}: no source in match state",
                    )
                )
                continue
            ok = abs(actual - c.value) <= c.tolerance + EPS
            checks.append(
                ClaimCheck(
                    claim=c,
                    actual=round(actual, 4),
                    ok=ok,
                    reason=None
                    if ok
                    else f"{c.metric} stated {c.value} but match state says {round(actual, 4)}",
                )
            )
        return checks

    @staticmethod
    def unsupported_numbers(text: str, claims: list[Claim], lang: Lang) -> list[str]:
        """Numbers in the text that no claim accounts for (an invented number)."""
        allowed: list[str] = []
        for c in claims:
            allowed.extend(numbers_in(fmt(c, lang)))
        pool = list(allowed)
        missing = []
        for n in numbers_in(text):
            if n in pool:
                pool.remove(n)
            elif n not in allowed:
                missing.append(n)
        return missing

    @staticmethod
    def unsupported_names(state: Blackboard, text: str, slots: dict[str, str]) -> list[str]:
        """Known teams or players the text mentions that the insight's brief does not name."""
        teams, players = known_names(state.meta)
        return name_violations(text, brief_names(slots), teams, players)

    def run(self, state: Blackboard, draft: Draft, lang: Lang = "en") -> Verdict:
        checks = self.check_claims(state, draft.claims)
        text = f"{draft.headline} {draft.body}"
        unsupported = self.unsupported_numbers(text, draft.claims, lang)
        names = self.unsupported_names(state, text, draft.slots)
        return Verdict(
            candidate_id=draft.candidate_id,
            attempt=draft.attempt,
            ok=all(c.ok for c in checks) and not unsupported and not names,
            checks=checks,
            unsupported_numbers=unsupported,
            unsupported_names=names,
        )

"""Verifier: checks every claim against the Blackboard, and every number in the text
against the claims. Nothing reaches air unless both checks pass.
"""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.generator import fmt, numbers_in
from whyitmatters.agents.models import Claim, ClaimCheck, Draft, Lang, Verdict
from whyitmatters.pulse.metrics import MinuteCounter

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
        if c.metric in ("possession_share", "pass_completion", "field_tilt", "turnovers_per_min"):
            if c.window is None:
                return None
            start, end = c.window
            w = self._counter(state, end).window(end, end - start + 1)
            if c.metric == "turnovers_per_min":
                return w.turnovers_per_min
            if c.side is None:
                return None
            team = w.home if c.side == "home" else w.away
            return float(getattr(team, c.metric))
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
        if c.metric == "carry_speed_kmh":
            return ev.ball_speed_kmh
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

    def run(self, state: Blackboard, draft: Draft, lang: Lang = "en") -> Verdict:
        checks = self.check_claims(state, draft.claims)
        unsupported = self.unsupported_numbers(f"{draft.headline} {draft.body}", draft.claims, lang)
        return Verdict(
            candidate_id=draft.candidate_id,
            attempt=draft.attempt,
            ok=all(c.ok for c in checks) and not unsupported,
            checks=checks,
            unsupported_numbers=unsupported,
        )

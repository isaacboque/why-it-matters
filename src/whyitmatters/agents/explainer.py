"""Explainer: writes why a moment matters, with a structured claim behind every number.

An optional `FaultInjector` makes the first draft mis-state a number (tests and the demo's
"unreliable model" switch). Retries read the source again.
"""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.faults import FaultInjector
from whyitmatters.agents.generator import TemplateGenerator, TextGenerator
from whyitmatters.agents.models import Claim, Draft, InsightCandidate, Verdict
from whyitmatters.schema import Side


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


class Explainer:
    name = "explainer"

    def __init__(self, generator: TextGenerator | None = None, faults: FaultInjector | None = None):
        self.generator = generator or TemplateGenerator()
        self.faults = faults

    def run(
        self,
        state: Blackboard,
        cand: InsightCandidate,
        attempt: int = 1,
        previous: Verdict | None = None,
    ) -> Draft:
        template, slots, claims = self._compose(state, cand)
        if attempt == 1 and self.faults is not None:
            claims = self.faults.corrupt(claims)
        headline, body = self.generator.render(template, "analyst", "en", slots, claims)
        slots = {**slots, "template": template}
        return Draft(
            candidate_id=cand.id,
            attempt=attempt,
            headline=headline,
            body=body,
            claims=claims,
            slots=slots,
        )

    # ------------------------------------------------------------------ composition
    def _compose(
        self, state: Blackboard, cand: InsightCandidate
    ) -> tuple[str, dict[str, str], list[Claim]]:
        names = {"home": state.team_name("home"), "away": state.team_name("away")}
        slots: dict[str, str] = {**names}
        if cand.side:
            slots["team"] = names[cand.side]
            slots["other"] = names[_other(cand.side)]
        if cand.player_id:
            slots["player"] = state.player_name(cand.player_id)

        if cand.kind == "state_shift":
            tr = next(t for t in state.transitions if t.id == cand.transition_id)
            w = tr.after
            win = (w.start_minute, w.end_minute)
            window_claim = Claim(
                key="win",
                metric="window_minutes",
                unit="minutes",
                value=w.end_minute - w.start_minute + 1,
                window=win,
            )
            if cand.to_state in ("home_control", "away_control"):
                side: Side = "home" if cand.to_state == "home_control" else "away"
                tw = w.home if side == "home" else w.away
                return (
                    "shift_control",
                    slots,
                    [
                        Claim(
                            key="poss",
                            metric="possession_share",
                            unit="share",
                            side=side,
                            value=tw.possession_share,
                            window=win,
                            tolerance=0.006,
                        ),
                        Claim(
                            key="comp",
                            metric="pass_completion",
                            unit="share",
                            side=side,
                            value=tw.pass_completion,
                            window=win,
                            tolerance=0.006,
                        ),
                        window_claim,
                    ],
                )
            if cand.to_state == "chaos":
                return (
                    "shift_chaos",
                    slots,
                    [
                        Claim(
                            key="turn",
                            metric="turnovers_per_min",
                            unit="rate",
                            value=w.turnovers_per_min,
                            window=win,
                            tolerance=0.06,
                        ),
                        window_claim,
                    ],
                )
            return (
                "shift_balanced",
                slots,
                [
                    Claim(
                        key="poss_h",
                        metric="possession_share",
                        unit="share",
                        side="home",
                        value=w.home.possession_share,
                        window=win,
                        tolerance=0.006,
                    ),
                    Claim(
                        key="poss_a",
                        metric="possession_share",
                        unit="share",
                        side="away",
                        value=w.away.possession_share,
                        window=win,
                        tolerance=0.006,
                    ),
                    window_claim,
                ],
            )

        ev = state.events[cand.event_id] if cand.event_id else None
        assert ev is not None, f"{cand.kind} needs an event"

        if cand.kind == "goal":
            pulse_state = state.pulse.state
            mine = "home_control" if ev.side == "home" else "away_control"
            theirs = "away_control" if ev.side == "home" else "home_control"
            slots["flow"] = (
                "flow_with"
                if pulse_state == mine
                else "flow_against"
                if pulse_state == theirs
                else "flow_chaos"
                if pulse_state == "chaos"
                else "flow_none"
            )
            return (
                "goal",
                slots,
                [
                    Claim(
                        key="sh",
                        metric="score_home",
                        unit="count",
                        value=ev.score_home,
                        event_id=ev.id,
                    ),
                    Claim(
                        key="sa",
                        metric="score_away",
                        unit="count",
                        value=ev.score_away,
                        event_id=ev.id,
                    ),
                    Claim(
                        key="xg",
                        metric="shot_xg",
                        unit="xg",
                        value=ev.xg or 0.0,
                        event_id=ev.id,
                        tolerance=0.001,
                    ),
                ],
            )
        if cand.kind == "big_chance":
            return (
                "big_chance",
                slots,
                [
                    Claim(
                        key="xg",
                        metric="shot_xg",
                        unit="xg",
                        value=ev.xg or 0.0,
                        event_id=ev.id,
                        tolerance=0.001,
                    ),
                    Claim(
                        key="xgpct",
                        metric="shot_xg",
                        unit="share",
                        value=ev.xg or 0.0,
                        event_id=ev.id,
                        tolerance=0.006,
                    ),
                ],
            )
        if cand.kind == "top_speed":
            return (
                "top_speed",
                slots,
                [
                    Claim(
                        key="kmh",
                        metric="carry_speed_kmh",
                        unit="kmh",
                        value=ev.ball_speed_kmh or 0.0,
                        event_id=ev.id,
                        tolerance=0.5,
                    ),
                ],
            )
        if cand.kind == "pass_master":
            return (
                "pass_master",
                slots,
                [
                    Claim(
                        key="n",
                        metric="player_completed_passes",
                        unit="count",
                        value=state.stats[cand.player_id or ""].completed_at.get(ev.id, 0),
                        player_id=cand.player_id,
                        event_id=ev.id,
                    ),
                ],
            )
        raise ValueError(f"unknown insight kind {cand.kind}")

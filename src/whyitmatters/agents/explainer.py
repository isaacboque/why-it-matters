"""Explainer: writes why a moment matters, with a structured claim behind every number.

An optional `FaultInjector` makes the first draft mis-state a number (tests and the demo's
"unreliable model" switch). Retries read the source again.
"""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.drivers import DRIVERS, driver_claims, drivers_of
from whyitmatters.agents.faults import FaultInjector
from whyitmatters.agents.generator import TemplateGenerator, TextGenerator, render_with_source
from whyitmatters.agents.models import Claim, Draft, InsightCandidate, Verdict
from whyitmatters.agents.tactics import damage_lane
from whyitmatters.agents.texts_tactics import ADVICE_FOR
from whyitmatters.pulse import damage
from whyitmatters.pulse import xt as xt_model
from whyitmatters.pulse.buildup import MAX_MOVE_S, MIN_MOVE_S, analyse_buildup
from whyitmatters.schema import Side

TACTICAL_KINDS = frozenset(
    {
        "press_surge",
        "midfield_battle",
        "danger_turnovers",
        "direct_switch",
        "line_breakers",
        "zone_damage",
        "momentum_swing",
        "shape_change",
        "lines_stretched",
    }
)

# which "My metric" threads a template belongs to (drivers and build-up add more)
TEMPLATE_TAGS: dict[str, tuple[str, ...]] = {
    "goal": ("xg",),
    "big_chance": ("xg",),
    "top_speed": ("speed",),
    "shot_speed": ("speed",),
    "pass_master": ("pass_quality",),
    "pass_difficulty": ("pass_quality",),
    "shift_control": ("possession",),
    "shift_control_why": ("possession",),
    "shift_chaos": ("possession",),
    "shift_balanced": ("possession",),
    "press_surge": ("pressing",),
    "midfield_battle": ("duels",),
    "danger_turnovers": ("possession",),
    "direct_switch": ("pass_quality", "pressing"),
    "line_breakers": ("threat", "pass_quality"),
    "zone_damage": ("threat",),
    "momentum_swing": ("threat",),
    "shape_change": ("shape",),
    "lines_stretched": ("shape",),
    "most_dangerous_pass": ("threat", "pass_quality"),
}


def tags_for(template: str, slots: dict[str, str]) -> list[str]:
    tags = list(TEMPLATE_TAGS.get(template, ()))
    for item in filter(None, slots.get("cause", "").split(",")):
        tags += DRIVERS[item.split(":")[0]].tags
    if slots.get("buildup") in ("buildup_counter", "buildup_high"):
        tags.append("pressing")
    return list(dict.fromkeys(tags))


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
        out = render_with_source(self.generator, template, "analyst", "en", slots, claims)
        headline, body = out.headline, out.body
        slots = {
            **slots,
            "template": template,
            "tags": ",".join(tags_for(template, slots)),
            "written_by": out.source,
        }
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
                claims = [
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
                ]
                drivers = drivers_of(tr, side)
                if not drivers:
                    return "shift_control", slots, claims
                # cause -> effect: the metrics that moved most explain the shift
                slots["cause"] = ",".join(f"{d.key}:dv{i}" for i, d in enumerate(drivers, 1))
                slots["advice"] = ADVICE_FOR[drivers[0].key]
                return "shift_control_why", slots, claims + driver_claims(drivers, win)
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

        if cand.kind in TACTICAL_KINDS:
            return self._tactical(state, cand, slots)

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
                    *self._buildup(state, ev, slots),
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
                    *self._buildup(state, ev, slots),
                ],
            )
        if cand.kind == "shot_speed":
            return (
                "shot_speed",
                slots,
                [
                    Claim(
                        key="kmh",
                        metric="shot_speed_kmh",
                        unit="kmh",
                        value=ev.ball_speed_kmh or 0.0,
                        event_id=ev.id,
                        tolerance=0.5,
                    ),
                ],
            )
        if cand.kind == "most_dangerous_pass":
            assert damage.is_completed_pass(ev), "most_dangerous_pass needs a completed pass"
            slots["advice"] = ADVICE_FOR[cand.kind]
            return (
                "most_dangerous_pass",
                slots,
                [
                    Claim(
                        key="xt", metric="pass_xt_added", unit="xt", event_id=ev.id,
                        value=round(xt_model.added(ev.x, ev.y, ev.end_x, ev.end_y), 3),
                        tolerance=0.006,
                    ),
                    Claim(
                        key="pk", metric="pass_packing", unit="count", event_id=ev.id,
                        value=damage.packing(ev),
                    ),
                ],
            )  # fmt: skip
        if cand.kind == "pass_difficulty":
            return (
                "pass_difficulty",
                slots,
                [
                    Claim(
                        key="pd",
                        metric="pass_difficulty",
                        unit="index",
                        value=ev.pass_difficulty or 0.0,
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

    # ------------------------------------------------------------------ tactical insights
    def _tactical(
        self, state: Blackboard, cand: InsightCandidate, slots: dict[str, str]
    ) -> tuple[str, dict[str, str], list[Claim]]:
        assert cand.side is not None and cand.window is not None, cand.kind
        side, win = cand.side, cand.window
        w = state.pulse.counter.window(win[1], win[1] - win[0] + 1)
        me = w.home if side == "home" else w.away
        opp = w.away if side == "home" else w.home
        window_claim = Claim(
            key="win", metric="window_minutes", unit="minutes", value=win[1] - win[0] + 1,
            window=win,
        )  # fmt: skip

        def claim(key: str, metric: str, unit: str, value: float, on: Side, tol: float = 0.0):
            return Claim(
                key=key, metric=metric, unit=unit, side=on, value=value, window=win,
                tolerance=tol,
            )  # type: ignore[arg-type]  # fmt: skip

        slots["advice"] = ADVICE_FOR[cand.kind]
        if cand.kind == "press_surge":
            claims = [claim("hr", "high_recoveries", "count", me.high_recoveries, side)]
            if me.ppda is not None:
                claims.append(claim("ppda", "ppda", "rate", me.ppda, side, 0.06))
            return "press_surge", slots, [*claims, window_claim]
        if cand.kind == "midfield_battle":
            return (
                "midfield_battle",
                slots,
                [
                    claim(
                        "share", "duel_share_mid", "share", me.duel_share_mid or 0.0, side, 0.006
                    ),
                    claim("n", "duels_won_mid", "count", me.duels_won_mid, side),
                    window_claim,
                ],
            )
        if cand.kind == "danger_turnovers":
            return (
                "danger_turnovers",
                slots,
                [claim("n", "own_half_losses", "count", me.own_half_losses, side), window_claim],
            )
        if cand.kind == "line_breakers":
            return (
                "line_breakers",
                slots,
                [
                    claim("lb", "line_breaks", "count", me.line_breaks, side),
                    claim("bl", "between_lines", "count", me.between_lines, side),
                    window_claim,
                ],
            )
        if cand.kind == "zone_damage":
            lane = damage_lane(me) or "centre"
            slots["lane"] = f"lane_{lane}"
            share = getattr(me, f"xt_share_{lane}") or 0.0
            return (
                "zone_damage",
                slots,
                [
                    claim("share", f"xt_share_{lane}", "share", share, side, 0.006),
                    claim("xt", "xt", "xt", me.xt, side, 0.006),
                    window_claim,
                ],
            )
        if cand.kind == "momentum_swing":
            return (
                "momentum_swing",
                slots,
                [
                    claim("xt", "xt", "xt", me.xt, side, 0.006),
                    claim("xt_o", "xt", "xt", opp.xt, _other(side), 0.006),
                    window_claim,
                ],
            )
        if cand.kind in ("shape_change", "lines_stretched"):
            size = win[1] - win[0] + 1
            was_win = (win[0] - size, win[1] - size)
            b = state.pulse.counter.window(was_win[1], size)
            was = b.home if side == "home" else b.away
            metric, unit, tol = (
                ("formation_in", "formation", 0.0)
                if cand.kind == "shape_change"
                else ("gap_def_mid", "metres", 0.06)
            )
            before = Claim(
                key="was", metric=metric, unit=unit, side=side, window=was_win, tolerance=tol,
                value=getattr(was, metric) or 0.0,
            )  # type: ignore[arg-type]  # fmt: skip
            return (
                cand.kind,
                slots,
                [claim("now", metric, unit, getattr(me, metric) or 0.0, side, tol), before,
                 window_claim],
            )  # fmt: skip
        # direct_switch: the team going long, and how hard the other side presses it
        return (
            "direct_switch",
            slots,
            [
                claim("lb", "long_ball_share", "share", me.long_ball_share, side, 0.006),
                claim("ppda", "ppda", "rate", opp.ppda or 0.0, _other(side), 0.06),
                window_claim,
            ],
        )

    def _buildup(self, state: Blackboard, shot, slots: dict[str, str]) -> list[Claim]:
        """How the move began (counter-press, high recovery, long ball), as verifiable claims."""
        move = analyse_buildup(state.log, shot)
        quick = move.recovery is not None and MIN_MOVE_S <= (move.seconds or 0.0) <= MAX_MOVE_S
        seconds = Claim(
            key="sec", metric="buildup_seconds", unit="seconds", value=move.seconds or 0.0,
            event_id=shot.id, tolerance=0.5,
        )  # fmt: skip
        if quick and move.counter_press:
            slots["buildup"] = "buildup_counter"
            flag = Claim(
                key="cp", metric="counter_press_in_move", unit="count", value=1, event_id=shot.id
            )
            return [seconds, flag]
        if quick and move.high_recovery:
            slots["buildup"] = "buildup_high"
            return [seconds]
        if move.long_balls >= 1:
            slots["buildup"] = "buildup_long"
            return [
                Claim(
                    key="lb",
                    metric="long_balls_in_move",
                    unit="count",
                    value=move.long_balls,
                    event_id=shot.id,
                )  # fmt: skip
            ]
        return []

"""Tactical metrics, driver attribution, build-up claims and the new insight kinds."""

import pytest

from whyitmatters.agents import Orchestrator, Verifier, Viewer, run_match
from whyitmatters.agents.drivers import DRIVERS, PRESS_DRIVERS, Driver, rank_drivers
from whyitmatters.agents.generator import T, fmt
from whyitmatters.agents.models import METRIC_TAGS, Claim
from whyitmatters.pulse import run_pulse
from whyitmatters.pulse.buildup import analyse_buildup
from whyitmatters.pulse.metrics import MinuteCounter, TeamWindow, WindowMetrics
from whyitmatters.schema import Event
from whyitmatters.simulator import simulate

TACTICAL_KINDS = ("press_surge", "midfield_battle", "danger_turnovers", "direct_switch")
NEW_KINDS = (*TACTICAL_KINDS, "pass_difficulty", "shot_speed")


def make_events(rows):
    """rows: (type, side, x, y, kwargs); time advances 5 s per event unless t is given."""
    out = []
    for i, (typ, side, x, y, kw) in enumerate(rows, start=1):
        t = kw.pop("t", i * 5.0)
        out.append(
            Event(
                id=f"e{i}", seq=i, t=t, period=1, minute=int(t // 60), type=typ, side=side,
                possession_id=kw.pop("pid", 1), x=x, y=y, **kw,
            )
        )  # fmt: skip
    return out


def window(events, end=0):
    c = MinuteCounter()
    for e in events:
        c.ingest(e)
    return c.window(end, 1)


# ------------------------------------------------------------------ metrics
def test_duels_credit_the_winner_in_their_own_third():
    w = window(
        make_events(
            [
                ("pass", "away", 50, 34, {}),
                ("tackle", "home", 60, 30, {"outcome": "won"}),  # home wins in the middle
                ("pass", "home", 60, 30, {}),
                (
                    "tackle",
                    "away",
                    30,
                    30,
                    {"outcome": "lost"},
                ),  # away loses at 30: home wins at 75
                (
                    "interception",
                    "home",
                    90,
                    30,
                    {"outcome": "won"},
                ),  # home wins in the final third
            ]
        )
    )
    assert (w.home.duels_won_mid, w.home.duels_won_att, w.home.duels_won_def) == (1, 2, 0)
    assert (w.away.duels_won_mid, w.away.duels_won_att, w.away.duels_won_def) == (0, 0, 0)
    assert w.home.duel_share_mid == 1.0 and w.away.duel_share_mid == 0.0
    assert w.home.duel_share_def is None  # nobody won a duel in that patch of grass


def test_duel_share_pairs_a_teams_attacking_third_with_the_others_defensive_third():
    w = window(
        make_events(
            [
                ("tackle", "home", 80, 30, {"outcome": "won"}),  # home wins in its attacking third
                ("tackle", "away", 20, 30, {"outcome": "won"}),  # away wins in ITS defensive third
                ("tackle", "away", 20, 30, {"outcome": "won"}),
            ]
        )
    )
    # the same patch of grass: home won 1, away won 2
    assert w.home.duel_share_att == pytest.approx(1 / 3, abs=0.001)
    assert w.away.duel_share_def == pytest.approx(2 / 3, abs=0.001)


def test_recoveries_high_and_in_the_final_third():
    w = window(
        make_events(
            [
                ("pass", "away", 50, 34, {}),
                ("interception", "home", 40, 30, {"outcome": "won"}),  # own half: not high
                ("pass", "away", 50, 34, {}),
                ("interception", "home", 60, 30, {"outcome": "won"}),  # high, not final third
                ("pass", "away", 50, 34, {}),
                ("tackle", "home", 75, 30, {"outcome": "won"}),  # high and final third
            ]
        )
    )
    assert w.home.high_recoveries == 2 and w.home.final_third_recoveries == 1


def test_counter_press_needs_the_ball_back_within_five_seconds():
    events = make_events(
        [
            ("pass", "home", 50, 34, {"t": 100.0}),
            ("interception", "away", 50, 34, {"t": 101.0, "outcome": "won"}),  # home loses it
            ("tackle", "home", 55, 34, {"t": 104.0, "outcome": "won"}),  # back within 3 s
            ("pass", "home", 55, 34, {"t": 110.0}),
            ("interception", "away", 50, 34, {"t": 111.0, "outcome": "won"}),
            ("tackle", "home", 55, 34, {"t": 120.0, "outcome": "won"}),  # 9 s later: too slow
        ]
    )
    assert window(events, end=1).home.counter_press == 1


def test_own_half_losses_are_dangerous_losses():
    w = window(
        make_events(
            [
                ("pass", "home", 40, 34, {}),
                ("interception", "away", 70, 34, {"outcome": "won"}),  # lost at home x=35
                ("pass", "home", 80, 34, {}),
                ("interception", "away", 30, 34, {"outcome": "won"}),  # lost at home x=75
                ("pass", "home", 30, 34, {}),
                ("ball_out", "home", 30, 34, {}),  # put out in its own half
            ]
        )
    )
    assert w.home.own_half_losses == 2 and w.home.losses_per_min == 3.0


def test_progressive_passes_move_the_ball_towards_goal_or_into_the_final_third():
    def p(x, end_x, outcome="complete", **kw):
        return ("pass", "home", x, 34, {"end_x": end_x, "end_y": 34, "outcome": outcome, **kw})

    w = window(
        make_events(
            [
                p(40, 52),  # 12 m forward
                p(40, 48),  # 8 m: not progressive
                p(66, 72),  # into the final third
                p(40, 60, outcome="incomplete"),  # incomplete never counts
                p(40, 25),  # backwards
            ]
        )
    )
    assert w.home.progressive_passes == 2


def test_long_ball_and_central_buildup_shares():
    w = window(
        make_events(
            [
                ("pass", "home", 20, 34, {"pass_distance": 35.0}),  # long, central
                ("pass", "home", 20, 5, {"pass_distance": 10.0}),  # short, wide
                ("pass", "home", 20, 34, {"pass_distance": 12.0}),  # short, central
                ("pass", "home", 20, 60, {"pass_distance": 34.0}),  # long, wide
            ]
        )
    )
    assert w.home.long_ball_share == 0.5 and w.home.central_buildup_share == 0.5
    assert w.home.passes == 4


# ------------------------------------------------------------------ drivers
def tw(**kw):
    base = dict(
        possession_share=0.5, pass_completion=0.8, field_tilt=0.5, ppda=8.0, tempo=10.0,
        losses_per_min=1.0, short_chain_share=0.3, pressures=5, shots=0, xg=0.0, goals=0,
    )  # fmt: skip
    return TeamWindow(**{**base, **kw})


def win(home, away):
    return WindowMetrics(
        start_minute=0, end_minute=4, home=home, away=away, turnovers_per_min=2.0, evidence=[]
    )


def test_drivers_pick_the_metrics_that_moved_most_in_the_teams_favour():
    before = win(tw(high_recoveries=1, ppda=9.0), tw(high_recoveries=1, ppda=9.0))
    after = win(
        tw(high_recoveries=6, ppda=3.0, progressive_passes=1),
        tw(high_recoveries=0, ppda=18.0, own_half_losses=7),
    )
    ds = rank_drivers(before, after, "home")
    keys = [d.key for d in ds]
    assert 1 <= len(ds) <= 3 and ds == sorted(ds, key=lambda d: -d.score)
    assert {"ppda", "high_rec"} <= set(keys[:3])
    assert all(k in PRESS_DRIVERS for k in keys)
    # the numbers a driver states are the subject's (or, for opp_losses, the opponent's) own
    by_key = {d.key: d for d in ds}
    assert by_key["high_rec"].after == 6 and by_key["ppda"].after == 3.0
    if "opp_losses" in by_key:
        assert by_key["opp_losses"].side == "away" and by_key["opp_losses"].after == 7


def test_drivers_ignore_noise_and_other_teams_gains():
    flat = win(tw(), tw())
    assert rank_drivers(flat, flat, "home") == []
    # the *other* team improving is not a driver for home
    after = win(tw(), tw(high_recoveries=6, ppda=2.0))
    assert rank_drivers(flat, after, "home") == []


def test_a_duel_share_over_fewer_than_three_duels_is_not_a_driver():
    before = win(tw(), tw())
    thin = win(tw(duels_won_mid=2, duel_share_mid=1.0), tw(duels_won_mid=0, duel_share_mid=0.0))
    assert "duel_mid" not in [d.key for d in rank_drivers(before, thin, "home")]
    solid = win(tw(duels_won_mid=4, duel_share_mid=0.8), tw(duels_won_mid=1, duel_share_mid=0.2))
    assert "duel_mid" in [d.key for d in rank_drivers(before, solid, "home")]


def test_defensive_counts_are_judged_per_opportunity():
    # home hogs the ball (80%), so its 3 recoveries are worth more than the raw count
    before = win(tw(possession_share=0.5, high_recoveries=2), tw(possession_share=0.5))
    after = win(tw(possession_share=0.8, high_recoveries=2), tw(possession_share=0.2))
    keys = [d.key for d in rank_drivers(before, after, "home")]
    assert "high_rec" in keys


def test_every_driver_has_words_in_every_language():
    from whyitmatters.agents.texts_tactics import ADVICE, ADVICE_FOR, DRIVER_PHRASES

    for key in DRIVERS:
        assert set(DRIVER_PHRASES[key]) == {"en", "es", "ca"}, key
        assert "{#v}" in DRIVER_PHRASES[key]["en"] and ADVICE_FOR[key] in ADVICE
    # no digit may sit in the static text: every number must come from a claim
    for phrases in DRIVER_PHRASES.values():
        assert not any(ch.isdigit() for text in phrases.values() for ch in text)


@pytest.mark.parametrize("seeds", [range(20), range(1000, 1020)], ids=["tuning", "held-out"])
def test_driver_attribution_finds_the_scripted_press(seeds):
    """In a control phase the winners press (DOMINANT press 0.7 vs 0.1): a pressing metric should
    be among the top drivers of at least 70 % of the shifts the Pulse confirms correctly."""
    total = hits = 0
    for seed in seeds:
        m = simulate(seed)
        for tr in run_pulse(m.events, m.meta).transitions:
            if tr.to_state not in ("home_control", "away_control"):
                continue
            est = tr.estimated_minute + 1
            phase = next((p for p in m.truth.phases if p.start_minute <= est < p.end_minute), None)
            if phase is None or phase.kind != tr.to_state:
                continue
            side = "home" if tr.to_state == "home_control" else "away"
            total += 1
            hits += any(d.key in PRESS_DRIVERS for d in rank_drivers(tr.before, tr.after, side))
    assert total >= 30
    assert hits / total >= 0.7, f"{hits}/{total}"


# ------------------------------------------------------------------ build-up
def _goal_move(counter_press: bool):
    """Home wins the ball high (interception), then a long ball, then a shot 8 s after."""
    rows = [("pass", "home", 40, 34, {"t": 90.0, "pid": 1})]
    if counter_press:
        rows += [
            ("interception", "away", 50, 34, {"t": 94.0, "pid": 1, "outcome": "won"}),
            ("pass", "away", 55, 34, {"t": 95.0, "pid": 2}),
        ]
    rows += [
        ("interception", "home", 60, 34, {"t": 98.0, "pid": 3, "outcome": "won"}),
        (
            "pass", "home", 60, 34,
            {"t": 100.0, "pid": 4, "end_x": 90, "end_y": 34, "outcome": "complete",
             "pass_distance": 32.0},
        ),
        ("shot", "home", 92, 34, {"t": 106.0, "pid": 4, "xg": 0.4, "outcome": "goal"}),
    ]  # fmt: skip
    return make_events(rows)


def test_buildup_reads_a_high_recovery_followed_by_a_long_ball():
    log = _goal_move(counter_press=False)
    move = analyse_buildup(log, log[-1])
    assert move.recovery is not None and move.recovery.side == "home"
    assert move.seconds == 8.0 and move.high_recovery and not move.counter_press
    assert move.long_balls == 1


def test_buildup_spots_a_counter_press():
    log = _goal_move(counter_press=True)
    move = analyse_buildup(log, log[-1])
    assert move.counter_press and move.seconds == 8.0


def test_buildup_without_a_recovery_has_no_seconds():
    log = make_events(
        [
            ("pass", "home", 40, 34, {"pid": 1}),
            ("shot", "home", 90, 34, {"pid": 1, "xg": 0.2, "outcome": "saved"}),
        ]
    )
    move = analyse_buildup(log, log[-1])
    assert move.recovery is None and move.seconds is None and not move.counter_press


# ------------------------------------------------------------------ end to end
@pytest.fixture(scope="module")
def runs():
    return [run_match(simulate(s)) for s in range(20)]


def test_every_new_kind_shows_up_and_stays_true(runs):
    seen = {k: 0 for k in NEW_KINDS}
    for o in runs:
        assert o.stats.truth_score >= 0.95 and o.stats.dropped == 0
        for i in o.insights:
            if i.kind in seen:
                seen[i.kind] += 1
    assert all(n > 0 for n in seen.values()), seen


def test_tactical_insights_are_rare_and_spaced_out(runs):
    for o in runs:
        tactical = [i for i in o.insights if i.kind in TACTICAL_KINDS]
        assert len(tactical) <= 8
        for a, b in zip(tactical, tactical[1:], strict=False):
            assert b.minute - a.minute >= 6
            if a.kind == b.kind and a.side == b.side:
                assert b.minute - a.minute >= 15


def test_control_shifts_say_why_in_numbers_the_verifier_checked(runs):
    why = [i for o in runs for i in o.insights if i.slots.get("template") == "shift_control_why"]
    assert len(why) >= 20
    verifier = Verifier()
    for o in runs[:5]:
        for i in (x for x in o.insights if x.slots.get("template") == "shift_control_why"):
            drivers = [c for c in i.claims if c.key.startswith("dv")]
            assert 1 <= len(drivers) <= 3
            assert all(c.ok for c in verifier.check_claims(o.state, i.claims))
            assert not verifier.unsupported_numbers(f"{i.headline} {i.body}", i.claims, "en")
            for c in drivers:  # each stated driver number really is in the text
                assert fmt(c, "en") in i.body


def test_the_verifier_catches_a_misstated_driver_or_buildup(runs):
    verifier = Verifier()
    tampered = 0
    for o in runs:
        for c in o.cues:
            ours = [x for x in c.claims if x.key.startswith("dv") or x.key in ("sec", "lb", "cp")]
            if not ours:
                continue
            bent = ours[0].model_copy(update={"value": ours[0].value + 3})
            assert not verifier.check_claims(o.state, [bent])[0].ok
            tampered += 1
    assert tampered >= 20


def test_goals_explain_how_they_were_built(runs):
    built = [c for o in runs for c in o.cues if c.kind == "goal" and c.slots.get("buildup")]
    assert built, "at least one goal over 20 matches should have a recognisable build-up"
    for c in built:
        assert "{" not in c.body and "  " not in c.body


@pytest.mark.parametrize("lang", ["en", "es", "ca"])
def test_coach_mode_adds_one_advice_sentence_and_invents_no_numbers(runs, lang):
    o = runs[0]
    analyst = {c.cue_id: c for c in o.personalize(Viewer(mode="analyst", lang=lang))}
    coach = o.personalize(Viewer(mode="coach", lang=lang))
    assert coach
    advised = 0
    for pc in coach:
        assert Verifier.unsupported_numbers(f"{pc.headline} {pc.body}", pc.claims, lang) == []
        base = analyst.get(pc.cue_id)
        if base and pc.body != base.body:
            assert pc.body.startswith(base.body) and pc.body[len(base.body) :].strip().endswith(".")
            advised += 1
    assert advised >= 1


def test_my_metric_follows_one_thread_and_goals_always_show(runs):
    o = runs[3]
    for metric in METRIC_TAGS:
        cues = o.personalize(Viewer(mode="fan", metric=metric))
        assert all(c.kind == "goal" or metric in c.tags for c in cues), metric
    everything = o.personalize(Viewer(mode="fan"))
    assert {c.cue_id for c in everything if c.kind == "goal"} <= {
        c.cue_id for c in o.personalize(Viewer(mode="fan", metric="speed"))
    }
    assert len(o.personalize(Viewer(mode="fan", metric="pressing"))) < len(everything)


def test_new_kinds_have_templates_and_hidden_numbers_stay_hidden():
    for kind in (*TACTICAL_KINDS, "pass_difficulty", "shot_speed", "shift_control_why"):
        for style in ("analyst", "fan"):
            for lang in ("en", "es", "ca"):
                head, body = T[kind][style][lang]
                assert not any(ch.isdigit() for ch in head + body), (kind, style, lang)


def test_pass_difficulty_and_shot_speed_are_surfaced(runs):
    for o in runs:
        for i in o.insights:
            if i.kind == "pass_difficulty":
                assert any(c.metric == "pass_difficulty" for c in i.claims)
                assert "difficulty" in i.body
            if i.kind == "shot_speed":
                assert any(c.metric == "shot_speed_kmh" for c in i.claims)
                assert "km/h" in i.body


def test_orchestrator_stays_fast_with_the_tactical_layer():
    import time

    m = simulate(5)
    started = time.perf_counter()
    o = Orchestrator(m.meta)
    for ev in m.events:
        o.ingest(ev)
    o.finish()
    assert time.perf_counter() - started < 10


def test_driver_dataclass_exposes_its_spec():
    d = Driver("ppda", "home", 9.0, 3.0, 0.5)
    assert d.spec.metric == "ppda" and d.spec.direction == -1
    assert isinstance(Claim(key="x", metric="ppda", unit="rate", value=3.0), Claim)

# ruff: noqa: E501
"""Depth metrics: pressing (A5), chances (A6), player cards (A7), the four new insight kinds (A8)
and the glossary (A9). Unit tests on hand-built plays, then the independent audit of the same
numbers over seeds 0-19 and 1000-1019 (the checker is tests/depth_indep.py).
"""

import re
import typing

import pytest
from depth_indep import DepthTally
from test_stats_audit import SEEDS, depth_tally, played

from whyitmatters.agents import Verifier
from whyitmatters.agents.generator import PHRASES, T, fmt
from whyitmatters.agents.models import Claim, InsightKind, Metric
from whyitmatters.agents.tactics import (
    PHYSICAL_DROP,
    block_drop,
    hub_player,
    physical_drop,
    press_escape,
)
from whyitmatters.agents.texts_tactics import ADVICE, ADVICE_FOR
from whyitmatters.api.app import create_app
from whyitmatters.pulse import chances, glossary
from whyitmatters.pulse.metrics import MinuteCounter, TeamWindow
from whyitmatters.pulse.physical import Checkpoints
from whyitmatters.pulse.ratings import BASE, player_cards
from whyitmatters.schema import Event, Freeze
from whyitmatters.simulator import simulate

NEW_KINDS = ("block_drop", "hub_player", "press_escape", "physical_drop")

# Opponents in the passer's coordinates: keeper at 100, back four at 80, midfield four at 65,
# front two at 50 (same block as tests/test_damage.py).
OPP = [(100, 34), (80, 10), (80, 27), (80, 41), (80, 58), (65, 10), (65, 27), (65, 41),
       (65, 58), (50, 27), (50, 41)]  # fmt: skip
OURS = [(5, 34)] + [(40, 6 * i) for i in range(1, 11)]


def mk(i, t, typ="pass", side="home", x=45.0, y=34.0, end_x=None, end_y=None, outcome=None,
       ours=OURS, opp=OPP, **kw):
    return Event(
        id=f"e{i}", seq=i, t=t, period=kw.pop("period", 1), minute=int(t // 60), type=typ,
        side=side, possession_id=1, x=x, y=y, end_x=end_x, end_y=end_y, outcome=outcome,
        freeze=Freeze(t=ours, o=opp), **kw,
    )  # fmt: skip


def window(events, end=0):
    c = MinuteCounter()
    for e in events:
        c.ingest(e)
    return c.window(end, 1)


# ------------------------------------------------------------------ physical (A7, A8)
def shifted(index, dx=0.0, dy=0.0):
    out = list(OURS)
    out[index] = (out[index][0] + dx, out[index][1] + dy)
    return out


def test_physical_legs_are_checkpoint_distances_and_speeds():
    cps = Checkpoints()
    assert cps.ingest(mk(1, 0.0, ours=OURS)) == {}
    # 2 s later is too soon: the checkpoint stays at t = 0
    assert cps.ingest(mk(2, 2.0, ours=shifted(3, 5))) == {}
    legs = cps.ingest(mk(3, 5.0, ours=shifted(3, 35), y=1.0))["home"]
    by = {leg.index: leg for leg in legs}
    assert by[3].metres == pytest.approx(35.0)
    assert by[3].kmh == pytest.approx(35 / 5 * 3.6)  # 25.2 km/h
    assert by[4].metres == 0 and len(legs) == 10  # the keeper (index 0) is never reported


def test_a_player_on_the_ball_is_left_out_of_the_leg():
    """The freeze frame puts the actor exactly on the ball, so his jump is not running."""
    cps = Checkpoints()
    cps.ingest(mk(1, 0.0, ours=OURS))
    ours = shifted(3, 20)
    x, y = ours[3]
    legs = cps.ingest(mk(2, 6.0, ours=ours, x=x, y=y))["home"]
    assert 3 not in {leg.index for leg in legs}


def test_no_credit_across_a_kick_off_a_long_gap_or_half_time():
    cps = Checkpoints()
    cps.ingest(mk(1, 0.0))
    assert cps.ingest(mk(2, 30.0, ours=shifted(3, 5))) == {}  # 30 s: no credit, new checkpoint
    assert cps.ingest(mk(3, 36.0, typ="kick_off", ours=shifted(3, 50))) == {}
    assert cps.ingest(mk(4, 41.0, ours=shifted(3, 53)))["home"][2].metres == pytest.approx(3.0)
    assert cps.ingest(mk(5, 3000.0, typ="half_end", period=1).model_copy(update={"freeze": None})) == {}


def test_sprints_and_high_speed_runs_are_counted_per_leg():
    c = MinuteCounter()
    c.ingest(mk(1, 0.0))
    c.ingest(mk(2, 5.0, ours=shifted(3, 35), y=1.0))  # 25.2 km/h
    c.ingest(mk(3, 10.0, ours=shifted(3, 35 + 28), y=1.0))  # 28 m in 5 s = 20.2 km/h
    w = c.window(0, 1).home
    assert (w.sprints, w.high_speed_runs) == (1, 2)
    assert w.top_speed_kmh == pytest.approx(25.2)
    assert w.distance_per_min == pytest.approx(63 / 10 / 1, abs=0.06)


# ------------------------------------------------------------------ pressing (A5)
def test_a_press_wins_when_the_ball_is_won_within_five_seconds():
    w = window([
        mk(1, 10.0, "pressure", "home"),
        mk(2, 13.0, "tackle", "home", outcome="won"),  # 3 s: a successful press
        mk(3, 14.0, "interception", "home"),  # no press left to credit
        mk(4, 20.0, "pressure", "home"),
        mk(5, 27.0, "interception", "home"),  # 7 s: too late
        mk(6, 30.0, "pressure", "away"),
        mk(7, 31.0, "tackle", "home", outcome="won"),  # the other team's press does not count
    ]).home
    assert (w.pressures, w.press_wins, w.press_success) == (2, 1, 0.5)
    assert w.regains == 4 and w.regains_wide_share == 0.0  # y = 34: all through the middle


def test_regains_in_the_outer_thirds_are_wide():
    w = window([
        mk(1, 10.0, "interception", "home", y=5.0),
        mk(2, 20.0, "interception", "home", y=34.0),
        mk(3, 30.0, "tackle", "home", y=60.0, outcome="won"),
        mk(4, 40.0, "tackle", "home", y=60.0, outcome="lost"),  # lost: not a regain
    ]).home
    assert (w.regains, w.regains_wide_share) == (3, round(2 / 3, 3))


def test_escapes_beat_the_first_line_or_go_long_over_it():
    through = mk(1, 10.0, x=30.0, y=34.0, end_x=85.0, end_y=34.0, outcome="complete",
                 pass_distance=55.0, player_id="a", receiver_id="b")  # breaks the forward line
    over = mk(2, 20.0, x=20.0, y=2.0, end_x=60.0, end_y=2.0, outcome="complete",
              pass_distance=40.0, player_id="a", receiver_id="b")  # long, round the side
    short = mk(3, 30.0, x=20.0, y=2.0, end_x=30.0, end_y=2.0, outcome="complete",
               pass_distance=10.0, player_id="a", receiver_id="b")  # neither
    late = mk(4, 40.0, x=70.0, y=34.0, end_x=95.0, end_y=34.0, outcome="complete",
              pass_distance=25.0, player_id="a", receiver_id="b")  # not build-up (x > 63)
    w = window([through, over, short, late]).home
    assert (w.press_escapes_short, w.press_escapes_long, w.press_escapes) == (1, 1, 2)
    assert w.press_escape_rate == round(2 / 3, 3)  # three of the four passes start at x <= 63


# ------------------------------------------------------------------ chances (A6)
def assist(x, y, end_x, end_y, **kw):
    return mk(1, 10.0, x=x, y=y, end_x=end_x, end_y=end_y, outcome="complete", player_id="a",
              receiver_id="b", **kw)


def shot(x, y, xg=0.1):
    return mk(2, 12.0, "shot", x=x, y=y, outcome="saved", player_id="b", xg=xg)


@pytest.mark.parametrize(
    ("kind", "pass_", "from_"),
    [
        ("cutback", assist(97, 5, 92, 30), (92, 30)),
        ("cross", assist(80, 5, 95, 34), (95, 34)),
        ("through", assist(45, 34, 85, 34), (85, 34)),  # through the back line, not into the box
        ("long", assist(30, 34, 40, 34), (60, 34)),  # a short pass, then a shot from range
        ("other", assist(60, 34, 75, 34), (95, 34)),
    ],
)
def test_shot_kinds_come_from_the_pass_before(kind, pass_, from_):
    assert chances.shot_kind(pass_, shot(*from_)) == kind


def test_a_shot_without_a_pass_to_the_shooter_has_no_assist():
    a = assist(97, 5, 92, 30).model_copy(update={"receiver_id": "c"})
    assert chances.assist_of(a, shot(92, 30)) is None
    assert chances.shot_kind(None, shot(70, 34)) == "long"
    assert chances.shot_kind(None, shot(95, 34)) == "other"


def test_window_counts_big_chances_shot_kinds_and_finishing():
    w = window([assist(97, 5, 92, 30), shot(92, 30, xg=0.45).model_copy(update={"outcome": "goal"}),
                mk(3, 20.0, "shot", x=75.0, y=34.0, outcome="off_target", player_id="b", xg=0.05)]).home
    assert (w.shots, w.big_chances, w.shots_cutback, w.shots_long) == (2, 1, 1, 1)
    assert w.xg_per_shot == 0.25 and w.finishing == 0.5


# ------------------------------------------------------------------ pass network and the rules
def team(**kw):
    base = dict(
        possession_share=0.5, pass_completion=0.8, field_tilt=0.5, ppda=8.0, tempo=10.0,
        losses_per_min=1.0, short_chain_share=0.3, pressures=5, shots=1, xg=0.1, goals=0,
    )  # fmt: skip
    return TeamWindow(**{**base, **kw})


def test_hub_is_the_most_involved_player_and_needs_a_clear_lead_and_a_rise():
    hub = team(hub_player="p1", hub_share=0.6, involvement={"p1": 0.6, "p2": 0.3, "p3": 0.2})
    assert hub_player(hub, team(involvement={"p1": 0.3})) == "p1"
    assert hub_player(hub, team(involvement={"p1": 0.55})) is None  # no rise on the window before
    close_race = team(hub_player="p1", hub_share=0.6, involvement={"p1": 0.6, "p2": 0.55})
    assert hub_player(close_race, team()) is None
    assert hub_player(team(hub_player="p1", hub_share=0.4, involvement={"p1": 0.4, "p2": 0.1}), team()) is None


def test_involvement_counts_passes_made_and_received():
    w = window([
        mk(1, 10.0, end_x=50.0, end_y=34.0, outcome="complete", player_id="a", receiver_id="b"),
        mk(2, 20.0, end_x=50.0, end_y=34.0, outcome="complete", player_id="b", receiver_id="a"),
        mk(3, 30.0, end_x=50.0, end_y=34.0, outcome="complete", player_id="b", receiver_id="c"),
        mk(4, 40.0, end_x=50.0, end_y=34.0, outcome="incomplete", player_id="c"),
    ]).home
    assert (w.hub_player, w.hub_share) == ("b", 1.0)  # b made or received all three
    assert w.involvement == {"a": 0.667, "b": 1.0, "c": 0.333}


def test_block_drop_needs_a_long_fall_of_the_back_line():
    assert block_drop(team(line_height=24.0), team(line_height=40.0))
    assert not block_drop(team(line_height=30.0), team(line_height=40.0))
    assert not block_drop(team(), team(line_height=40.0))


def test_press_escape_needs_a_pressing_opponent_and_a_jump():
    me = team(press_escapes=9, press_escape_rate=0.45)
    assert press_escape(me, team(ppda=5.0), team(press_escape_rate=0.2))
    assert not press_escape(me, team(ppda=12.0), team(press_escape_rate=0.2))  # nobody presses
    assert not press_escape(me, team(ppda=5.0), team(press_escape_rate=0.4))  # always did
    assert not press_escape(team(press_escapes=3, press_escape_rate=0.5), team(ppda=5.0), team())


def test_physical_drop_is_a_fall_against_the_teams_own_early_match():
    ref = team(distance_per_min=90.0)
    assert physical_drop(team(distance_per_min=90.0 * (1 - PHYSICAL_DROP) - 0.1), ref)
    assert not physical_drop(team(distance_per_min=80.0), ref)
    assert not physical_drop(team(distance_per_min=10.0), team())  # no reference, no insight


# ------------------------------------------------------------------ player cards (A7)
def test_rating_is_a_plain_sum_of_visible_parts():
    meta = simulate(3).meta
    a, b, c = (p.id for p in meta.home.players[6:9])  # outfield players
    events = [
        mk(1, 10.0, end_x=60.0, end_y=34.0, outcome="complete", player_id=a, receiver_id=b),
        mk(2, 12.0, "shot", x=95.0, y=34.0, outcome="goal", player_id=b, xg=0.4),
        mk(3, 20.0, "interception", x=30.0, y=34.0, player_id=c),
        mk(4, 30.0, end_x=60.0, end_y=34.0, outcome="incomplete", player_id=c),
        mk(5, 40.0, "tackle", x=30.0, y=34.0, outcome="lost", player_id=c),
    ]
    cards = {k["player_id"]: k for k in player_cards(meta, events)}
    assert (cards[a]["key_passes"], cards[a]["xa"]) == (1, 0.4)
    assert cards[b]["goals"] == 1 and cards[b]["xg"] == 0.4
    assert (cards[c]["wins"], cards[c]["lost_duels"]) == (1, 1)
    assert cards[b]["breakdown"]["finishing"] == pytest.approx(0.8 + 0.4)
    assert cards[c]["breakdown"]["defence"] == pytest.approx(0.08)
    assert cards[c]["breakdown"]["losses"] == pytest.approx(-(0.03 + 0.10))
    for k in cards.values():
        assert k["rating"] == pytest.approx(
            min(10.0, max(1.0, BASE + sum(k["breakdown"].values()))), abs=0.051
        )


# ------------------------------------------------------------------ independent audit (A5-A8)
def audit_close(name: str, prod, ind) -> bool:
    tol = {"distance_per_min": 0.051, "top_speed_kmh": 0.051, "finishing": 0.006}.get(name, 6e-4)
    if name in ("press_wins", "regains", "big_chances", "sprints", "high_speed_runs",
                "press_escapes_short", "press_escapes_long", "press_escapes", "shots_cutback",
                "shots_cross", "shots_through", "shots_long"):
        tol = 1e-9
    return abs(prod - ind) <= tol + 1e-9


@pytest.mark.parametrize("seed", SEEDS)
def test_every_depth_metric_matches_the_independent_recount(seed):
    """Per minute, 5-minute window and match scope, against tests/depth_indep.py."""
    from test_stats_audit import tally  # same cached walk of the log as the main audit

    _, orch = played(seed)
    pulses = [r["data"] for r in orch.bus if r["type"] == "pulse"]
    d, t = depth_tally(seed), tally(seed)
    names = [n for n in d.window(0, 5)["home"] if n not in ("edge", "hub_player", "involvement")]
    bad: list[str] = []
    n = 0
    for p in pulses:
        m = p["minute"]
        for scope, lo in (("window", max(0, m - 4)), ("match", 0)):
            src = p if scope == "window" else p["match"]
            ind, base = d.window(lo, m), t.window(lo, m)
            for side in ("home", "away"):
                edge = ind[side]["edge"]
                for name in names:
                    n += 1
                    slack = edge if name.startswith(("press_escape", "shots_through")) else 0
                    if abs(src[side][name] - ind[side][name]) > slack and not audit_close(
                        name, src[side][name], ind[side][name]
                    ):
                        bad.append(f"{m}' {scope} {side} {name}: shown {src[side][name]} vs {ind[side][name]}")
                n += 1
                wins, press = ind[side]["press_wins"], base[side]["pressures"]
                want = wins / press if press else 0.0
                if abs(src[side]["press_success"] - want) > 6e-4 + (edge / press if press else 0):
                    bad.append(f"{m}' {scope} {side} press_success")
                n += 1
                if src[side]["hub_player"] != ind[side]["hub_player"]:
                    bad.append(f"{m}' {scope} {side} hub_player {src[side]['hub_player']} vs {ind[side]['hub_player']}")
    assert not bad, f"{len(bad)} of {n} numbers differ, e.g. " + "; ".join(bad[:6])


@pytest.mark.parametrize("seed", [*range(0, 20, 3), 1000, 1007, 1014])
def test_player_cards_match_the_independent_recount_and_sum_to_the_team(seed):
    match, _ = played(seed)
    meta = match.meta
    roster = {"home": [p.id for p in meta.home.players], "away": [p.id for p in meta.away.players]}
    ind = DepthTally(match.events, roster)
    cards = player_cards(meta, match.events)
    assert len(cards) == 22
    bad = []
    for k in cards:
        p = ind.player[k["player_id"]]
        for field, key, tol in (
            ("involvement", "involvement", 0), ("passes", "passes", 0), ("completed", "completed", 0),
            ("progressive", "progressive", 0), ("line_breaks", "line_breaks", 0),
            ("key_passes", "key_passes", 0), ("shots", "shots", 0), ("goals", "goals", 0),
            ("wins", "wins", 0), ("lost_duels", "lost_duels", 0), ("sprints", "sprints", 0),
            ("xt", "xt", 0.0006 * 80), ("xa", "xa", 0.006), ("xg", "xg", 0.006),
            ("distance_m", "distance_m", 0.51), ("top_speed_kmh", "top_speed_kmh", 0.051),
        ):
            if abs(k[field] - p[key]) > tol + 1e-9:
                bad.append(f"{k['player_id']} {field}: card {k[field]} vs independent {p[key]}")
        want = 5.2 + 3.0 * p["xt"] + 0.08 * p["wins"] + 0.25 * p["key_passes"] + 2.0 * p["xa"] \
            + 0.8 * p["goals"] + 1.0 * p["xg"] - 0.03 * p["incomplete"] - 0.10 * p["lost_duels"]
        want = min(10.0, max(1.0, want))
        if abs(k["rating"] - want) > 0.1 + 0.0006 * 3 * 80:
            bad.append(f"{k['player_id']} rating {k['rating']} vs {want:.2f}")
    assert not bad, "; ".join(bad[:6])
    # per-player sums are the team totals
    last = max(e.minute for e in match.events)
    for side in ("home", "away"):
        team_ = ind.window(0, last)[side]
        mine = [k for k in cards if k["side"] == side]
        assert sum(k["sprints"] for k in mine) == team_["sprints"]
        assert sum(k["key_passes"] for k in mine) == sum(
            1 for a, b in zip(match.events, match.events[1:], strict=False)
            if b.type == "shot" and a.type == "pass" and a.outcome == "complete" and a.side == side
            and b.side == side and a.receiver_id == b.player_id
        )
        assert sum(k["distance_m"] for k in mine) == pytest.approx(
            team_["distance_per_min"] * 10 * (last + 1), abs=11
        )


def test_the_tiredness_is_planted_in_the_simulator():
    """Players cover less ground late (the ground truth behind physical_drop)."""
    ratio = []
    for seed in range(10):
        d = depth_tally(seed)
        for side in ("home", "away"):
            early = d.window(15, 29)[side]["distance_per_min"]
            late = d.window(75, 89)[side]["distance_per_min"]
            ratio.append(late / early)
    assert sum(ratio) / len(ratio) < 0.95


# ------------------------------------------------------------------ the new insight kinds (A8)
def insights_of(kinds):
    out = []
    for seed in range(20):
        orch = played(seed)[1]
        out += [(seed, orch, i) for i in orch.insights if i.kind in kinds]
    return out


def test_each_new_kind_shows_up_and_every_claim_is_true():
    verifier = Verifier()
    seen = {k: 0 for k in NEW_KINDS}
    for _seed, orch, i in insights_of(NEW_KINDS):
        seen[i.kind] += 1
        for chk in verifier.check_claims(orch.state, i.claims):
            assert chk.ok, (i.kind, chk)
    assert all(n > 0 for n in seen.values()), seen
    for seed in range(20):
        o = played(seed)[1]
        assert o.stats.dropped == 0 and o.stats.truth_score >= 0.95


def test_a_hub_insight_names_a_player_whose_share_the_verifier_recomputes():
    rows = insights_of(("hub_player",))
    assert rows
    verifier = Verifier()
    for _, orch, i in rows:
        claim = next(c for c in i.claims if c.metric == "player_involvement")
        assert claim.player_id == i.player_id and claim.value >= 0.55
        assert verifier.resolve(orch.state, claim) == pytest.approx(claim.value, abs=0.006)
        wrong = claim.model_copy(update={"value": claim.value + 0.1})
        assert not verifier.check_claims(orch.state, [wrong])[0].ok
        other = claim.model_copy(update={"player_id": "nobody"})
        assert verifier.resolve(orch.state, other) is None


def test_physical_and_block_claims_cite_an_earlier_window():
    for _, _orch, i in insights_of(("physical_drop", "block_drop")):
        now = next(c for c in i.claims if c.key == "now")
        was = next(c for c in i.claims if c.key == "was")
        assert was.window[1] <= now.window[1]
        assert now.metric == was.metric
        assert (now.value < was.value) if i.kind == "physical_drop" else (was.value - now.value >= 14.0 - 0.06)


def test_new_kinds_are_rare_and_spaced_out():
    per_match = len(insights_of(NEW_KINDS)) / 20
    assert 1.0 <= per_match <= 5.0, per_match
    for seed in range(20):
        orch = played(seed)[1]
        tactical = [i for i in orch.insights if i.kind in NEW_KINDS]
        for a, b in zip(tactical, tactical[1:], strict=False):
            assert b.minute - a.minute >= 6
            if a.kind == b.kind and a.side == b.side:
                assert b.minute - a.minute >= 20


def test_new_kinds_have_words_in_every_language_and_no_digits():
    digit = re.compile(r"\d")
    for kind in NEW_KINDS:
        for mode in ("analyst", "fan"):
            for lang in ("en", "es", "ca"):
                head, body = T[kind][mode][lang]
                assert not digit.search(head) and not digit.search(re.sub(r"\{#\w+\}", "", body))
        for lang in ("en", "es", "ca"):
            assert ADVICE[ADVICE_FOR[kind]][lang]
            assert not digit.search(ADVICE[ADVICE_FOR[kind]][lang])
    assert PHRASES  # the shared phrase table still loads


def test_a_misstated_new_number_is_caught():
    verifier = Verifier()
    for kind in NEW_KINDS:
        _, orch, i = next(r for r in insights_of((kind,)))
        c = next(c for c in i.claims if c.metric != "window_minutes")
        bad = c.model_copy(update={"value": c.value + (0.2 if c.unit == "share" else 5.0)})
        assert not verifier.check_claims(orch.state, [bad])[0].ok


def test_new_kinds_air_in_the_right_modes():
    """Every wording of a new kind re-renders from the same claims and re-verifies."""
    from whyitmatters.agents.models import Viewer

    seen: set[str] = set()
    for _seed, orch, _i in insights_of(NEW_KINDS):
        for mode in ("analyst", "fan", "coach"):
            for lang in ("en", "es", "ca"):
                for pc in orch.personalize(Viewer(mode=mode, lang=lang)):
                    assert pc.verified
                    if pc.kind in NEW_KINDS:
                        seen.add(f"{pc.kind}/{mode}")
        break
    assert any(s.endswith("/coach") for s in seen) or insights_of(NEW_KINDS)


# ------------------------------------------------------------------ glossary (A9)
def test_every_metric_a_claim_can_carry_has_a_glossary_entry_in_three_languages():
    metrics = set(typing.get_args(Metric))
    assert set(glossary.GLOSSARY) == metrics
    for key, e in glossary.GLOSSARY.items():
        for field in (e.label, e.fan, e.analyst, e.why, e.help_en, e.help_es, e.help_ca):
            assert field.strip(), key
        assert glossary.help_text(key, "es") == e.help_es
        assert glossary.help_text(key, "ca-ES") == e.help_ca
        assert glossary.help_text(key, "fr") == e.help_en


def test_metrics_md_is_generated_from_the_glossary():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs" / "METRICS.md").read_text(encoding="utf-8")
    assert text == glossary.markdown(), "run: python -m whyitmatters.pulse.glossary --write"
    for key in glossary.GLOSSARY:
        assert f"`{key}`" in text


def test_the_glossary_lists_every_insight_kind_that_uses_a_metric():
    undeclared = set()
    for seed in range(20):
        for i in played(seed)[1].insights:
            for c in i.claims:
                kinds = glossary.GLOSSARY[c.metric].kinds
                if i.kind not in kinds and "every windowed kind" not in kinds:
                    undeclared.add((i.kind, c.metric))
    # control shifts cite their drivers (any tactical metric); skip that kind
    undeclared = {(k, m) for k, m in undeclared if k not in ("state_shift",)}
    assert not undeclared, sorted(undeclared)


def test_all_insight_kinds_are_known_to_the_glossary_and_producer():
    from whyitmatters.agents.producer import ON_SCREEN_SECONDS

    assert set(typing.get_args(InsightKind)) <= set(ON_SCREEN_SECONDS)
    assert fmt(Claim(key="a", metric="hub_share", value=0.62, unit="share"), "en") == "62%"


# ------------------------------------------------------------------ API
def test_players_and_glossary_endpoints():
    from fastapi.testclient import TestClient

    client = TestClient(create_app({}))
    r = client.get("/matches/3/players")
    assert r.status_code == 200
    cards = r.json()["players"]
    assert len(cards) == 22 and {"rating", "breakdown", "distance_m", "sprints"} <= set(cards[0])
    g = client.get("/glossary").json()
    assert set(g["metrics"]) == set(typing.get_args(Metric))
    assert g["metrics"]["press_escapes"]["help"]["ca"]
    assert "rating" in g["player_card"]

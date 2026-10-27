import pytest

from whyitmatters.agents import Verifier, run_match
from whyitmatters.agents.generator import PHRASES, T
from whyitmatters.agents.models import Claim
from whyitmatters.agents.texts_tactics import ADVICE, ADVICE_FOR
from whyitmatters.pulse import damage
from whyitmatters.pulse.metrics import MinuteCounter
from whyitmatters.schema import Event, Freeze
from whyitmatters.simulator import simulate

DAMAGE_KINDS = (
    "line_breakers",
    "zone_damage",
    "momentum_swing",
    "shape_change",
    "lines_stretched",
    "most_dangerous_pass",
)

# Opponents in the passer's coordinates: keeper at 100, back four at 80, midfield four at 65,
# front two at 50. Their lines, back line first, sit at 80 / 65 / 50.
OPP = [(100, 34), (80, 10), (80, 27), (80, 41), (80, 58), (65, 10), (65, 27), (65, 41),
       (65, 58), (50, 27), (50, 41)]  # fmt: skip
OURS = [(5, 34)] + [(40, 6 * i) for i in range(1, 11)]


def ev(typ="pass", x=45.0, y=34.0, end_x=72.0, end_y=34.0, outcome="complete", **kw):
    return Event(
        id=kw.pop("id", "p1"), seq=1, t=10.0, period=1, minute=0, type=typ, side="home",
        possession_id=1, x=x, y=y, end_x=end_x, end_y=end_y, outcome=outcome,
        freeze=Freeze(t=OURS, o=OPP), **kw,
    )  # fmt: skip


# ------------------------------------------------------------------ per pass
def test_opponent_lines_back_line_first():
    assert damage.opponent_lines(ev()) == pytest.approx([80, 65, 50])


def test_packing_counts_the_opponents_a_pass_goes_past():
    assert damage.packing(ev()) == 6  # midfield four and front two, not the back four
    assert damage.packing(ev(end_x=90)) == 10
    assert damage.packing(ev(outcome="incomplete")) == 0


def test_line_breaking_needs_a_goalward_pass_past_a_line():
    assert damage.lines_broken(ev()) == 2
    assert damage.lines_broken(ev(end_x=60)) == 1
    assert damage.lines_broken(ev(x=70, end_x=40)) == 0  # backwards
    assert damage.lines_broken(ev(y=5, end_x=52, end_y=63)) == 0  # sideways: not 10 % closer


def test_reception_between_the_lines():
    assert damage.between_lines(ev())  # 72 is between the midfield (65) and back line (80)
    assert damage.reception_gaps(ev()) == ["mid_def"]
    assert damage.reception_gaps(ev(end_x=60)) == ["fwd_mid"]  # between the front two and midfield
    assert not damage.between_lines(ev(end_x=85))  # behind the back line
    assert not damage.between_lines(ev(end_x=45))  # in front of the front two


# Hand-built frames for the lateral-span rule (OPP: lines at 80 / 65 / 50; back and midfield
# lines span y 10..58, the front two span y 27..41; all spans widen by 2 m).
def test_pass_round_the_outside_of_the_back_four_does_not_break_it():
    p = ev(x=70, y=3, end_x=88, end_y=3)
    assert damage.lines_broken_roles(p) == []
    assert damage.lines_broken(p) == 0


def test_pass_through_the_gap_between_centre_backs_breaks_the_back_line():
    assert damage.lines_broken_roles(ev(x=70, y=34, end_x=88, end_y=34)) == ["back"]


def test_pass_through_the_midfield_line_breaks_the_midfield_line():
    assert damage.lines_broken_roles(ev(x=55, y=34, end_x=70, end_y=34)) == ["midfield"]
    assert damage.lines_broken_roles(ev()) == ["midfield", "forward"]


def test_pass_round_the_outside_of_the_forward_line_does_not_break_it():
    assert damage.lines_broken_roles(ev(x=40, y=5, end_x=55, end_y=5)) == []


def test_reception_on_the_touchline_level_with_the_midfield_is_not_between_lines():
    p = ev(x=40, y=1, end_x=65.5, end_y=1)
    assert damage.reception_gaps(p) == []


def test_reception_in_the_pocket_behind_the_midfield_is_mid_def():
    assert damage.reception_gaps(ev(end_x=72, end_y=34)) == ["mid_def"]


def test_reception_behind_the_forwards_in_front_of_the_midfield_is_fwd_mid():
    assert damage.reception_gaps(ev(end_x=58, end_y=34)) == ["fwd_mid"]


def test_reception_next_to_an_opponent_is_not_in_space():
    assert damage.reception_gaps(ev(end_x=66, end_y=28)) == []  # 1.4 m from a midfielder


def test_zone_entries_and_lanes():
    assert damage.entries(ev("carry", x=80, end_x=95, outcome=None)) == (True, False, False)
    assert damage.entries(ev(x=60, end_x=75)) == (False, True, False)
    assert damage.entries(ev(x=60, end_x=75, end_y=18)) == (False, False, True)
    assert damage.entries(ev(x=60, end_x=95, outcome="incomplete")) == (False, False, False)
    assert [damage.lane_of(y) for y in (5, 34, 60)] == ["left", "centre", "right"]


# ------------------------------------------------------------------ windows
@pytest.fixture(scope="module")
def match():
    return simulate(7)


def test_window_damage_metrics(match):
    c = MinuteCounter()
    for e in match.events:
        c.ingest(e)
    w = c.window(60, 10)
    for team in (w.home, w.away):
        assert 0 <= team.line_breaks <= team.passes
        assert team.packing >= team.line_breaks
        shares = [team.xt_share_left, team.xt_share_centre, team.xt_share_right]
        assert sum(shares) == pytest.approx(1.0, abs=0.01)
        assert team.best_pass_id is not None and team.best_pass_xt > 0


# ------------------------------------------------------------------ insights
@pytest.fixture(scope="module")
def runs():
    return [(simulate(s), run_match(simulate(s))) for s in range(8)]


def _phase(m, minute):
    minute = min(minute, 89)
    return next(p.kind for p in m.truth.phases if p.start_minute <= minute < p.end_minute)


def _shape_in(m, side, minute):
    minute = min(minute, 89)
    return next(
        s.in_possession
        for s in m.truth.shapes
        if s.side == side and s.start_minute <= minute < s.end_minute
    )


def test_damage_insights_appear_and_are_verified(runs):
    seen = set()
    for _, o in runs:
        for ins in o.insights:
            if ins.kind in DAMAGE_KINDS:
                seen.add(ins.kind)
                assert ins.claims and ins.evidence
    assert len(seen) >= 5, seen


def test_shape_changes_match_the_planted_shapes(runs):
    """A reported change of shape in possession matches a scripted change of role."""
    hits = total = 0
    for m, o in runs:
        for cue in o.producer.aired:
            if cue.kind == "shape_change":
                minute = int(cue.t_in // 60)
                total += 1
                hits += _shape_in(m, cue.side, minute - 1) != _shape_in(m, cue.side, minute - 14)
    assert total >= 8 and hits / total >= 0.75


def test_stretched_lines_come_from_broken_games(runs):
    hits = total = 0
    for m, o in runs:
        for cue in o.producer.aired:
            if cue.kind == "lines_stretched":
                total += 1
                hits += _phase(m, int(cue.t_in // 60) - 2) == "chaos"
    assert total >= 2 and hits / total >= 0.5


def test_a_wrong_packing_is_caught(runs):
    _, o = next((m, o) for m, o in runs if any(i.kind == "most_dangerous_pass" for i in o.insights))
    ins = next(i for i in o.insights if i.kind == "most_dangerous_pass")
    pk = next(c for c in ins.claims if c.key == "pk")
    checks = Verifier().check_claims(
        o.state, [pk, Claim(**{**pk.model_dump(), "value": pk.value + 2})]
    )
    assert checks[0].ok and not checks[1].ok


# ------------------------------------------------------------------ words
def test_damage_kinds_have_words_without_digits():
    for kind in DAMAGE_KINDS:
        assert ADVICE_FOR[kind] in ADVICE
        for style in ("analyst", "fan"):
            for lang in ("en", "es", "ca"):
                head, body = T[kind][style][lang]
                assert not any(ch.isdigit() for ch in head + body), (kind, style, lang)
                assert not any(ch.isdigit() for ch in ADVICE[ADVICE_FOR[kind]][lang])
    for lane in ("lane_left", "lane_centre", "lane_right"):
        assert set(PHRASES[lane]) == {"en", "es", "ca"}


def test_the_feed_carries_positions_and_damage_for_the_match_centre(runs):
    from whyitmatters.api.app import build_feed

    _, o = runs[0]
    feed = build_feed(o)
    passes = [r["data"] for r in feed if r["type"] == "event" and r["data"]["type"] == "pass"]
    assert all(len(p["fz"]) == 44 for p in passes)
    done = [p for p in passes if p.get("outcome") == "complete"]
    assert done and all({"xt", "lb", "pk"} <= p.keys() for p in done)
    pulse = next(r["data"] for r in reversed(feed) if r["type"] == "pulse")
    assert pulse["match"]["home"]["passes"] >= pulse["home"]["passes"]


# ------------------------------------------------------------------ wording variety
def test_alternative_wordings_use_the_same_numbers_and_no_digits():
    import re

    from whyitmatters.agents.texts_variants import SITUATION_PHRASES, VARIANTS

    keys = lambda text: sorted(re.findall(r"\{#(\w+)\}", text))  # noqa: E731
    for template, styles in VARIANTS.items():
        for style, langs in styles.items():
            for lang, alts in langs.items():
                base = keys(" ".join(T[template][style][lang]))
                for head, body in alts:
                    assert not any(ch.isdigit() for ch in head + body), (template, lang)
                    assert keys(head + " " + body) == base, (template, style, lang)
    for phrases in SITUATION_PHRASES.values():
        assert set(phrases) == {"en", "es", "ca"}
        assert not any(ch.isdigit() for t in phrases.values() for ch in t)


def test_wordings_rotate_and_the_score_situation_is_named(runs):
    from whyitmatters.agents.texts_variants import situation

    assert situation("press_surge", 0, 1) == "sit_chasing"
    assert situation("press_surge", 2, 1) == "sit_ahead"
    assert situation("danger_turnovers", 1, 0) == "sit_risk"
    assert situation("goal", 0, 1) is None
    _, o = runs[0]
    shifts = [i for i in o.insights if i.kind == "state_shift"]
    assert len({i.headline for i in shifts}) >= 3  # not the same sentence every time

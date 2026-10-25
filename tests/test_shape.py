import math

import pytest

from whyitmatters.agents.generator import fmt
from whyitmatters.agents.models import Claim
from whyitmatters.eval.shape import ShapeScore, score_shapes
from whyitmatters.pulse import xt
from whyitmatters.pulse.metrics import MinuteCounter
from whyitmatters.pulse.shape import (
    block_of,
    detect_lines,
    formation_code,
    hull_area,
    possession_side,
    summarize,
)
from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, EventType
from whyitmatters.simulator import simulate
from whyitmatters.simulator.positions import IN_SHAPES, MAX_SPEED, out_shape


@pytest.fixture(scope="module")
def match():
    return simulate(7)


def _avg_from(template: dict[str, tuple[float, float]], line: float = 30.0):
    """11 positions (GK first) from a positions.py template, in SLOT order."""
    order = ("RB2", "CB4", "CB5", "LB3", "DM6", "CM8", "CM10", "RW7", "ST9", "LW11")
    return [(5.0, 34.0)] + [(line + template[k][0], template[k][1]) for k in order]


# ---------------------------------------------------------------- line detection
@pytest.mark.parametrize(
    "template, label",
    [
        (out_shape("4-4-2", 11), "4-4-2"),
        (out_shape("4-5-1", 9), "4-5-1"),
        (IN_SHAPES["4-3-3"], "4-3-3"),
        (IN_SHAPES["3-2-5"], "3-2-5"),
    ],
)
def test_templates_are_detected(template, label):
    assert summarize(_avg_from(template)).formation == label


def test_lines_are_back_to_front():
    pts = [(10, 10), (10, 30), (10, 50), (25, 20), (25, 40), (40, 34)]
    lines = detect_lines(pts)
    assert [len(x) for x in lines] == [3, 2, 1]


def test_hull_area_of_a_square():
    assert hull_area([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)]) == pytest.approx(100.0)


def test_shape_summary_numbers():
    s = summarize(_avg_from(out_shape("4-4-2", 11), line=30.0))
    assert s.line_height == pytest.approx(30.0)
    assert s.gap_def_mid == pytest.approx(11.0)
    assert s.length == pytest.approx(22.0)


def test_block_thresholds():
    assert block_of(40) == "high" and block_of(25) == "mid" and block_of(12) == "low"


def test_formation_code_round_trips_through_fmt():
    c = Claim(key="f", metric="formation_out", value=formation_code("4-2-3-1"),
              unit="formation", side="home", window=(1, 5))
    assert fmt(c, "en") == "4-2-3-1"


# ---------------------------------------------------------------- freeze frames
def test_every_on_ball_event_has_a_frame(match):
    for ev in match.events:
        if ev.type == EventType.HALF_END:
            continue
        assert ev.freeze is not None
        assert len(ev.freeze.t) == 11 and len(ev.freeze.o) == 11
        for x, y in ev.freeze.t + ev.freeze.o:
            assert 0 <= x <= PITCH_LENGTH and 0 <= y <= PITCH_WIDTH


def test_actor_stands_at_the_event(match):
    team = {"home": match.meta.home, "away": match.meta.away}
    for ev in match.events[:400]:
        if ev.player_id and ev.freeze:
            idx = [p.id for p in team[ev.side].players].index(ev.player_id)
            fx, fy = ev.freeze.t[idx]
            assert abs(fx - ev.x) < 0.11 and abs(fy - ev.y) < 0.11


def test_players_move_at_human_speeds(match):
    """Off the ball, nobody teleports: displacement <= max speed x time (+ jitter)."""
    prev = None
    for ev in match.events[:600]:
        if ev.side != "home" or ev.freeze is None or ev.type == EventType.KICK_OFF:
            prev = None
            continue
        if prev is not None:
            p_ev, p_frame = prev
            dt = max(0.5, ev.t - p_ev.t)
            for i, ((x0, y0), (x1, y1)) in enumerate(zip(p_frame, ev.freeze.t, strict=True)):
                if match.meta.home.players[i].id in (ev.player_id, p_ev.player_id):
                    continue
                assert math.hypot(x1 - x0, y1 - y0) <= MAX_SPEED * dt + 6
        prev = (ev, ev.freeze.t)


def test_possession_side_for_defensive_actions(match):
    tackle = next(e for e in match.events if e.type == EventType.TACKLE)
    assert possession_side(tackle) != tackle.side


def test_truth_lists_a_shape_per_phase_and_team(match):
    assert len(match.truth.shapes) == 2 * len(match.truth.phases)


def test_same_seed_same_frames():
    a, b = simulate(3), simulate(3)
    assert a.events[100].freeze == b.events[100].freeze


# ---------------------------------------------------------------- xT
def test_xt_grows_towards_goal():
    assert xt.value(100, 34) > xt.value(80, 34) > xt.value(50, 34) > xt.value(10, 34)


def test_xt_added_is_end_minus_start():
    assert xt.added(50, 34, 95, 34) == pytest.approx(xt.value(95, 34) - xt.value(50, 34))
    assert xt.added(95, 34, 50, 34) < 0


def test_window_reports_shape_and_xt(match):
    c = MinuteCounter()
    for ev in match.events:
        c.ingest(ev)
    w = c.window(40, 5)
    for team in (w.home, w.away):
        assert team.shape_out is not None and team.line_height is not None
        assert team.formation_out is not None
        assert len(team.xt_zone) == 18


def test_shape_detection_quality_on_tuning_seeds():
    total = ShapeScore()
    for seed in range(6):
        total.add(score_shapes(simulate(seed)))
    d = total.as_dict()
    assert d["formation_out_accuracy"] >= 0.65
    assert d["formation_in_accuracy"] >= 0.8
    assert d["block_accuracy"] >= 0.6

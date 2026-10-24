from collections import Counter

import pytest

from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, EventType, Outcome
from whyitmatters.simulator import read_match, simulate, write_match
from whyitmatters.simulator.teams import CLUBS
from whyitmatters.simulator.xg import expected_goals


@pytest.fixture(scope="module")
def match():
    return simulate(7)


def test_same_seed_same_match():
    a, b = simulate(3), simulate(3)
    assert a.model_dump() == b.model_dump()


def test_different_seeds_differ():
    assert simulate(3).events[50].model_dump() != simulate(4).events[50].model_dump()


def test_events_are_ordered_and_unique(match):
    seqs = [e.seq for e in match.events]
    assert seqs == sorted(seqs)
    assert len({e.id for e in match.events}) == len(match.events)
    times = [(e.period, e.t) for e in match.events]
    assert times == sorted(times)


def test_coordinates_on_pitch(match):
    for e in match.events:
        assert 0 <= e.x <= PITCH_LENGTH and 0 <= e.y <= PITCH_WIDTH
        if e.end_x is not None:
            assert 0 <= e.end_x <= PITCH_LENGTH and 0 <= e.end_y <= PITCH_WIDTH


def test_score_matches_goals(match):
    goals = Counter(
        e.side for e in match.events if e.type == EventType.SHOT and e.outcome == Outcome.GOAL
    )
    last = match.events[-1]
    assert (last.score_home, last.score_away) == (goals["home"], goals["away"])


@pytest.mark.parametrize("seed", range(10))
def test_realistic_volumes(seed):
    m = simulate(seed)
    passes = [e for e in m.events if e.type == EventType.PASS]
    shots = [e for e in m.events if e.type == EventType.SHOT]
    completion = sum(e.outcome == Outcome.COMPLETE for e in passes) / len(passes)
    assert 900 <= len(passes) <= 1300
    assert 12 <= len(shots) <= 40
    assert 0.70 <= completion <= 0.90


def test_pass_quality_fields(match):
    for e in match.events:
        if e.type == EventType.PASS:
            assert e.pass_distance is not None and e.pass_distance >= 0
            assert 0 <= e.pass_difficulty <= 1
            assert 15 <= e.ball_speed_kmh <= 120


def test_ground_truth_covers_the_match(match):
    phases = match.truth.phases
    assert phases[0].start_minute == 0 and phases[-1].end_minute == 90
    for a, b in zip(phases, phases[1:], strict=False):
        assert a.end_minute == b.start_minute
        assert a.kind != b.kind


def test_key_moments_point_at_shots(match):
    by_id = {e.id: e for e in match.events}
    for km in match.truth.key_moments:
        ev = by_id[km.event_id]
        assert ev.type == EventType.SHOT
        assert km.kind == "goal" or ev.xg >= 0.3


def test_fictional_names_only(match):
    club_names = {c[0] for c in CLUBS}
    assert match.meta.home.name in club_names and match.meta.away.name in club_names
    assert len(match.meta.home.players) == 11


def test_xg_is_monotonic_with_distance():
    assert expected_goals(99, 34) > expected_goals(90, 34) > expected_goals(80, 34)
    assert expected_goals(94, 34, under_pressure=True) < expected_goals(94, 34)


def test_jsonl_roundtrip(tmp_path, match):
    path = tmp_path / "m.jsonl"
    write_match(match, path)
    again = read_match(path)
    assert again.meta == match.meta
    assert again.truth == match.truth
    assert [e.id for e in again.events] == [e.id for e in match.events]

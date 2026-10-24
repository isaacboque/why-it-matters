import pytest

from whyitmatters.eval import score_match, summarize
from whyitmatters.pulse import MatchPulse, PulseSnapshot, Transition, classify, run_pulse
from whyitmatters.pulse.metrics import MinuteCounter
from whyitmatters.simulator import simulate


@pytest.fixture(scope="module")
def match():
    return simulate(7)


@pytest.fixture(scope="module")
def pulse(match):
    return run_pulse(match.events, match.meta)


def test_one_snapshot_per_minute(pulse, match):
    minutes = [s.minute for s in pulse.snapshots]
    assert minutes == list(range(match.events[-1].minute + 1))


def test_streaming_equals_batch(match, pulse):
    live = MatchPulse(match.meta)
    outputs = []
    for ev in match.events:
        outputs.extend(live.ingest(ev))
    outputs.extend(live.finish())
    snaps = [o for o in outputs if isinstance(o, PulseSnapshot)]
    trans = [o for o in outputs if isinstance(o, Transition)]
    assert [s.model_dump() for s in snaps] == [s.model_dump() for s in pulse.snapshots]
    assert [t.model_dump() for t in trans] == [t.model_dump() for t in pulse.transitions]


def test_indices_in_range(pulse):
    for s in pulse.snapshots:
        assert -1 <= s.dominance <= 1
        assert 0 <= s.chaos <= 1
        h, a = s.window.home, s.window.away
        if h.possession_share or a.possession_share:
            assert abs(h.possession_share + a.possession_share - 1) < 0.01


def test_transitions_change_state_and_cite_evidence(pulse):
    assert pulse.transitions, "a scripted match should produce at least one state change"
    for t in pulse.transitions:
        assert t.from_state != t.to_state
        assert t.estimated_minute <= t.detected_minute
    ids = {e for t in pulse.transitions for e in t.evidence}
    assert ids  # the Verifier needs something to check claims against


def test_classify_thresholds():
    assert classify(0.6, 0.1) == "home_control"
    assert classify(-0.6, 0.1) == "away_control"
    assert classify(0.0, 0.9) == "chaos"
    assert classify(0.05, 0.1) == "balanced"


def test_ppda_counts_only_press_zone_actions(match):
    c = MinuteCounter()
    for ev in match.events:
        c.ingest(ev)
    w = c.window(89, 90)
    for team in (w.home, w.away):
        assert team.ppda is None or team.ppda > 0


def test_detection_quality_on_tuning_seeds():
    """Guard rail on the seeds used for tuning; held-out seeds are checked by the eval CLI."""
    s = summarize([score_match(simulate(seed)) for seed in range(10)])
    assert s.recall >= 0.75
    assert s.precision >= 0.55
    assert s.timeline_accuracy >= 0.7

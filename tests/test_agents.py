import time

import pytest

from whyitmatters.agents import (
    Blackboard,
    Claim,
    Explainer,
    Orchestrator,
    Producer,
    TemplateGenerator,
    Verifier,
    Viewer,
    run_match,
)
from whyitmatters.agents.generator import T, fmt, numbers_in
from whyitmatters.agents.models import Insight, InsightCandidate
from whyitmatters.simulator import simulate


@pytest.fixture(scope="module")
def match():
    return simulate(7)


@pytest.fixture(scope="module")
def orch(match):
    return run_match(match)


def _fed_blackboard(match, upto=None):
    bb = Blackboard(match.meta)
    for ev in match.events[:upto]:
        bb.ingest(ev)
    return bb


# ---------------------------------------------------------------- generator
def test_every_template_exists_in_every_mode_and_language():
    for tid, modes in T.items():
        for style in ("analyst", "fan"):
            for lang in ("en", "es", "ca"):
                assert modes[style][lang], f"{tid}/{style}/{lang}"


def test_numbers_are_formatted_per_language():
    c = Claim(key="xg", metric="shot_xg", unit="xg", value=0.456, event_id="e")
    assert fmt(c, "en") == "0.46" and fmt(c, "ca") == "0,46"
    share = Claim(key="p", metric="possession_share", unit="share", value=0.684, side="home")
    assert fmt(share, "es") == "68%"


def test_template_generator_never_leaves_a_slot_unfilled():
    gen = TemplateGenerator()
    claims = [Claim(key=k, metric="score_home", unit="count", value=1, event_id="e")
              for k in ("sh", "sa", "xg")]
    for lang in ("en", "es", "ca"):
        h, b = gen.render("goal", "fan", lang, {"home": "A", "away": "B", "team": "A",
                                                "player": "P", "flow": "flow_with"}, claims)
        assert "{" not in h + b


# ---------------------------------------------------------------- verifier
def test_verifier_accepts_true_claims(match):
    bb = _fed_blackboard(match)
    shot = next(e for e in match.events if e.type == "shot")
    c = Claim(key="xg", metric="shot_xg", unit="xg", value=shot.xg, event_id=shot.id,
              tolerance=0.001)
    assert Verifier().check_claims(bb, [c])[0].ok


def test_verifier_rejects_a_wrong_number(match):
    bb = _fed_blackboard(match)
    shot = next(e for e in match.events if e.type == "shot")
    c = Claim(key="xg", metric="shot_xg", unit="xg", value=shot.xg + 0.2, event_id=shot.id,
              tolerance=0.001)
    check = Verifier().check_claims(bb, [c])[0]
    assert not check.ok and "stated" in check.reason


def test_verifier_rejects_an_invented_number():
    claims = [Claim(key="poss", metric="possession_share", unit="share", value=0.62,
                    side="home", window=(10, 14))]
    assert Verifier.unsupported_numbers("They have 62% of the ball", claims, "en") == []
    assert Verifier.unsupported_numbers("They have 62% and 7 shots", claims, "en") == ["7"]


def test_verifier_rejects_claim_without_source(match):
    bb = _fed_blackboard(match)
    c = Claim(key="x", metric="shot_xg", unit="xg", value=0.5, event_id="does-not-exist")
    assert not Verifier().check_claims(bb, [c])[0].ok


def test_fault_injected_drafts_are_caught(match):
    """A model that mis-states numbers on its first draft never gets them on air."""
    bb = _fed_blackboard(match)
    shot = next(e for e in match.events if e.type == "shot" and e.xg and e.xg >= 0.3)
    cand = InsightCandidate(id="in-x", kind="big_chance", minute=shot.minute, t=shot.t,
                            significance=0.6, side=shot.side, player_id=shot.player_id,
                            event_id=shot.id, evidence=[shot.id])
    bad = Explainer(fault_rate=1.0).run(bb, cand, attempt=1)
    verdict = Verifier().run(bb, bad)
    assert not verdict.ok and verdict.failures
    fixed = Explainer(fault_rate=1.0).run(bb, cand, attempt=2, previous=verdict)
    assert Verifier().run(bb, fixed).ok


# ---------------------------------------------------------------- producer
def _insight(i, t, kind="state_shift", sig=0.8):
    return Insight(id=f"in-{i}", kind=kind, minute=int(t // 60), t=t, significance=sig,
                   side="home", player_id=None, headline="h", body="b", claims=[], slots={},
                   evidence=[], attempts=1, latency_ms=0.1)


def test_producer_respects_budget():
    p = Producer(budget=2, window_min=5)
    aired = [p.run(_insight(i, 600 + i * 20)) for i in range(5)]
    assert sum(c is not None for c in aired) == 2


def test_goals_always_air():
    p = Producer(budget=1, window_min=5)
    p.run(_insight(1, 600))
    assert p.run(_insight(2, 610, kind="goal", sig=1.0)) is not None


# ---------------------------------------------------------------- end to end
@pytest.mark.parametrize("seed", range(5))
def test_end_to_end_truth_and_budget(seed):
    o = run_match(simulate(seed))
    assert o.stats.truth_score >= 0.95
    assert o.recap is not None
    for cue in o.cues:
        if cue.kind == "goal":
            continue
        recent = [c for c in o.cues if 0 <= cue.t_in - c.t_in < 300]
        assert len(recent) <= o.producer.budget + sum(c.kind == "goal" for c in recent)


def test_every_goal_gets_a_cue(match, orch):
    goals = [e.id for e in match.events if e.type == "shot" and e.outcome == "goal"]
    cued = {eid for c in orch.cues if c.kind == "goal" for eid in c.evidence_event_ids}
    assert set(goals) <= cued


def test_retries_recover_from_an_unreliable_model(match):
    o = run_match(match, fault_rate=0.5, seed=1)
    assert o.stats.first_draft_accuracy < 0.9
    assert o.stats.retries > 0
    assert o.stats.dropped == 0
    verifier = Verifier()
    for cue in o.cues:  # what aired is still all true
        assert all(c.ok for c in verifier.check_claims(o.state, cue.claims))


@pytest.mark.parametrize("lang", ["en", "es", "ca"])
@pytest.mark.parametrize("mode", ["analyst", "fan"])
def test_personalized_cues_invent_no_numbers(orch, mode, lang):
    cues = orch.personalize(Viewer(mode=mode, lang=lang))
    assert cues
    for pc in cues:
        assert Verifier.unsupported_numbers(f"{pc.headline} {pc.body}", pc.claims, lang) == []


def test_player_focus_and_favourite_club(orch, match):
    scorer = next(e.player_id for e in match.events if e.type == "shot" and e.outcome == "goal")
    side = orch.state.side_of(scorer)
    cues = orch.personalize(Viewer(mode="player_focus", club=side, player_id=scorer))
    assert any(pc.for_you for pc in cues)
    assert all(pc.kind in ("goal", "state_shift") or pc.for_you for pc in cues)


def test_recap_is_verified_and_lists_moments(orch):
    r = orch.recap
    assert r.moments and len(r.moments) <= 3
    assert all(numbers_in(m.headline) is not None for m in r.moments)
    assert Verifier.unsupported_numbers(f"{r.headline} {r.summary}", r.claims, "en") == []


def test_streaming_bus_has_every_stage(orch):
    kinds = {b["type"] for b in orch.bus}
    assert {"event", "pulse", "verdict", "insight", "cue", "recap", "trust"} <= kinds


def test_whole_match_runs_fast(match):
    started = time.perf_counter()
    o = Orchestrator(match.meta)
    for ev in match.events:
        o.ingest(ev)
    o.finish()
    assert time.perf_counter() - started < 10

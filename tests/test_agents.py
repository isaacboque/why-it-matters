import time

import pytest

from whyitmatters.agents import (
    Analyst,
    Blackboard,
    Claim,
    Explainer,
    FaultInjector,
    Orchestrator,
    Personalizer,
    Producer,
    RecapWriter,
    TemplateGenerator,
    Verifier,
    Viewer,
    run_match,
)
from whyitmatters.agents.generator import T, fmt, numbers_in
from whyitmatters.agents.models import Draft, Insight, InsightCandidate
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


def _big_chance_candidate(match):
    shot = next(e for e in match.events if e.type == "shot" and e.xg and e.xg >= 0.3)
    cand = InsightCandidate(
        id="in-x",
        kind="big_chance",
        minute=shot.minute,
        t=shot.t,
        significance=0.6,
        side=shot.side,
        player_id=shot.player_id,
        event_id=shot.id,
        evidence=[shot.id],
    )
    return shot, cand


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
    claims = [
        Claim(key=k, metric="score_home", unit="count", value=1, event_id="e")
        for k in ("sh", "sa", "xg")
    ]
    for lang in ("en", "es", "ca"):
        h, b = gen.render(
            "goal",
            "fan",
            lang,
            {"home": "A", "away": "B", "team": "A", "player": "P", "flow": "flow_with"},
            claims,
        )
        assert "{" not in h + b


# ---------------------------------------------------------------- blackboard
def test_blackboard_is_fed_only_by_the_stream(match):
    bb = _fed_blackboard(match, upto=300)
    assert len(bb.log) == 300
    assert not hasattr(bb, "truth") and not hasattr(bb, "phases")
    assert bb.score["home"] + bb.score["away"] == sum(
        e.outcome == "goal" for e in match.events[:300] if e.type == "shot"
    )


# ---------------------------------------------------------------- analyst
def _run_analyst(match):
    bb, analyst, out = Blackboard(match.meta), Analyst(), []
    for ev in match.events:
        out.extend(analyst.run(bb, ev, bb.ingest(ev)))
    return out


def test_analyst_finds_every_goal_and_big_chance(match):
    cands = _run_analyst(match)
    goals = {e.id for e in match.events if e.type == "shot" and e.outcome == "goal"}
    chances = {
        e.id
        for e in match.events
        if e.type == "shot" and e.outcome != "goal" and e.xg and e.xg >= 0.3
    }
    assert goals == {c.event_id for c in cands if c.kind == "goal"}
    assert chances == {c.event_id for c in cands if c.kind == "big_chance"}


@pytest.mark.parametrize("seed", range(20))
def test_analyst_does_not_repeat_itself(seed):
    cands = _run_analyst(simulate(seed))
    shifts = [c for c in cands if c.kind == "state_shift"]
    for a, b in zip(shifts, shifts[1:], strict=False):
        assert (a.to_state, a.side) != (b.to_state, b.side), "same shift twice in a row"
    for state in ("chaos", "balanced"):
        mins = [c.minute for c in shifts if c.to_state == state]
        assert all(y - x >= 12 for x, y in zip(mins, mins[1:], strict=False))
    masters = [c for c in cands if c.kind == "pass_master"]
    assert len(masters) <= 2


# ---------------------------------------------------------------- verifier
def test_verifier_accepts_true_claims(match):
    bb = _fed_blackboard(match)
    shot = next(e for e in match.events if e.type == "shot")
    c = Claim(
        key="xg", metric="shot_xg", unit="xg", value=shot.xg, event_id=shot.id, tolerance=0.001
    )
    assert Verifier().check_claims(bb, [c])[0].ok


def test_verifier_rejects_a_wrong_number(match):
    bb = _fed_blackboard(match)
    shot = next(e for e in match.events if e.type == "shot")
    c = Claim(
        key="xg",
        metric="shot_xg",
        unit="xg",
        value=shot.xg + 0.2,
        event_id=shot.id,
        tolerance=0.001,
    )
    check = Verifier().check_claims(bb, [c])[0]
    assert not check.ok and "stated" in check.reason


def test_verifier_rejects_an_invented_number():
    claims = [
        Claim(
            key="poss",
            metric="possession_share",
            unit="share",
            value=0.62,
            side="home",
            window=(10, 14),
        )
    ]
    assert Verifier.unsupported_numbers("They have 62% of the ball", claims, "en") == []
    assert Verifier.unsupported_numbers("They have 62% and 7 shots", claims, "en") == ["7"]


def test_verifier_rejects_claim_without_source(match):
    bb = _fed_blackboard(match)
    c = Claim(key="x", metric="shot_xg", unit="xg", value=0.5, event_id="does-not-exist")
    assert not Verifier().check_claims(bb, [c])[0].ok


def test_verifier_recomputes_windows_from_raw_events_not_the_live_counter(match):
    """A corrupted live counter must not be able to vouch for a wrong claim."""
    bb = _fed_blackboard(match)
    tr = bb.transitions[0]
    win = (tr.after.start_minute, tr.after.end_minute)
    true_value = tr.after.home.possession_share
    claim = Claim(
        key="p",
        metric="possession_share",
        unit="share",
        side="home",
        value=true_value,
        window=win,
        tolerance=0.006,
    )
    verifier = Verifier()
    assert verifier.check_claims(bb, [claim])[0].ok
    for minute in range(win[0], win[1] + 1):  # corrupt the live counter
        bb.pulse.counter.buckets[minute]["home"].poss_seconds += 500
    stale = Verifier()
    assert stale.check_claims(bb, [claim])[0].ok


def test_fault_injected_drafts_are_caught(match):
    """A model that mis-states numbers on its first draft never gets them on air."""
    bb = _fed_blackboard(match)
    _, cand = _big_chance_candidate(match)
    bad = Explainer(faults=FaultInjector(1.0)).run(bb, cand, attempt=1)
    verdict = Verifier().run(bb, bad)
    assert not verdict.ok and verdict.failures
    fixed = Explainer(faults=FaultInjector(1.0)).run(bb, cand, attempt=2, previous=verdict)
    assert Verifier().run(bb, fixed).ok


def test_fault_in_the_text_only_is_caught(match):
    """Claims are right but the words say a different number."""
    bb = _fed_blackboard(match)
    _, cand = _big_chance_candidate(match)
    good = Explainer().run(bb, cand)
    lie = Draft(**{**good.model_dump(), "body": good.body + " That is the 9th such chance."})
    verdict = Verifier().run(bb, lie)
    assert not verdict.ok and verdict.unsupported_numbers == ["9"]


@pytest.mark.parametrize("seed", range(5))
def test_every_claim_kind_is_caught_when_corrupted(seed):
    """Whatever the Explainer says, a mis-stated number in any claim fails verification."""
    m = simulate(seed)
    o = run_match(m)
    verifier = Verifier()
    assert o.insights
    for ins in o.insights:
        for i, c in enumerate(ins.claims):
            wrong = FaultInjector(1.0, seed=i)
            corrupted = wrong.corrupt([c])
            assert not verifier.check_claims(o.state, corrupted)[0].ok, (ins.kind, c.metric)


# ---------------------------------------------------------------- producer
def _insight(i, t, kind="state_shift", sig=0.8):
    return Insight(
        id=f"in-{i}",
        kind=kind,
        minute=int(t // 60),
        t=t,
        significance=sig,
        side="home",
        player_id=None,
        headline="h",
        body="b",
        claims=[],
        slots={},
        evidence=[],
        attempts=1,
        latency_ms=0.1,
    )


def test_producer_respects_budget():
    p = Producer(budget=2, window_min=5)
    aired = [p.run(_insight(i, 600 + i * 20)) for i in range(5)]
    assert sum(c is not None for c in aired) == 2
    assert len(p.held) == 3


def test_producer_budget_holds_at_air_time_not_arrival_time():
    """A cue delayed by the screen being busy still counts where it actually airs."""
    p = Producer(budget=3, window_min=5)
    for i in range(3):
        assert p.run(_insight(i, 1000 + i * 10)) is not None
    # arrives 250 s after the first aired cue, airs even later: window already holds 3
    assert p.run(_insight(9, 1000 + 250)) is None


def test_goals_always_air():
    p = Producer(budget=1, window_min=5)
    p.run(_insight(1, 600))
    assert p.run(_insight(2, 610, kind="goal", sig=1.0)) is not None


def test_low_significance_is_held():
    p = Producer()
    assert p.run(_insight(1, 600, sig=0.1)) is None and len(p.held) == 1


def test_cues_have_clean_json_for_a_graphics_partner(orch):
    for cue in orch.cues:
        d = cue.model_dump(mode="json")
        assert d["t_out"] > d["t_in"] and d["priority"] in (1, 2, 3)
        assert d["evidence_event_ids"] and d["verified"] is True


# ---------------------------------------------------------------- end to end
def _budget_ok(o):
    """When a non-goal cue airs, no rolling window containing it holds more than `budget` cues.
    (Goals always air, so a goal can later push a window over: that is by design.)"""
    w = o.producer.window_s
    times = [c.t_in for c in o.cues]
    for cue in o.cues:
        if cue.kind == "goal":
            continue
        for start in times:
            if start <= cue.t_in < start + w:
                aired = sum(start <= t <= cue.t_in for t in times)
                assert aired <= o.producer.budget


@pytest.mark.parametrize("seed", range(5))
def test_end_to_end_truth_and_budget(seed):
    started = time.perf_counter()
    o = run_match(simulate(seed))
    assert time.perf_counter() - started < 10
    assert o.stats.truth_score >= 0.95
    assert o.recap is not None
    _budget_ok(o)
    verifier = Verifier()
    for cue in o.cues:  # everything that aired is true
        assert all(c.ok for c in verifier.check_claims(o.state, cue.claims))
        assert verifier.unsupported_numbers(f"{cue.headline} {cue.body}", cue.claims, "en") == []


@pytest.mark.parametrize("seed", range(5))
def test_end_to_end_with_an_unreliable_model(seed):
    o = run_match(simulate(seed), fault_rate=0.3, seed=seed)
    assert o.stats.dropped == 0
    assert o.stats.truth_score >= 0.85  # raw claims incl. rejected drafts
    _budget_ok(o)
    verifier = Verifier()
    for cue in o.cues:
        assert all(c.ok for c in verifier.check_claims(o.state, cue.claims))


def test_every_goal_gets_a_cue(match, orch):
    goals = [e.id for e in match.events if e.type == "shot" and e.outcome == "goal"]
    cued = {eid for c in orch.cues if c.kind == "goal" for eid in c.evidence_event_ids}
    assert set(goals) <= cued


def test_retries_recover_from_an_unreliable_model(match):
    o = run_match(match, fault_rate=0.5, seed=1)
    assert o.stats.first_draft_accuracy < 0.9
    assert o.stats.retries > 0
    assert o.stats.dropped == 0


class _Liar:
    """A generator that always invents a number."""

    name = "liar"

    def render(self, template, mode, lang, slots, claims):
        return "Headline 99", "Body with 77 invented"


def test_a_generator_that_always_lies_never_reaches_air(match):
    o = run_match(match, generator=_Liar())
    assert o.cues == [] and o.stats.dropped > 0
    assert o.recap is not None  # the recap falls back to the offline writer


def test_latency_is_reported(orch):
    t = orch.trust()
    assert 0 < t["latency_ms_mean"] < 2000 and t["latency_ms_p95"] < 2000
    assert all(i.latency_ms < 2000 for i in orch.insights)


# ---------------------------------------------------------------- personalizer
@pytest.mark.parametrize("lang", ["en", "es", "ca"])
@pytest.mark.parametrize("mode", ["analyst", "fan"])
def test_personalized_cues_invent_no_numbers(orch, mode, lang):
    cues = orch.personalize(Viewer(mode=mode, lang=lang))
    assert cues
    for pc in cues:
        assert Verifier.unsupported_numbers(f"{pc.headline} {pc.body}", pc.claims, lang) == []


def test_languages_differ_but_numbers_agree(orch):
    en = orch.personalize(Viewer(lang="en"))
    ca = orch.personalize(Viewer(lang="ca"))
    assert [c.cue_id for c in en] == [c.cue_id for c in ca]
    assert [c.headline for c in en] != [c.headline for c in ca]
    for a, b in zip(en, ca, strict=True):
        assert [n.replace(",", ".") for n in numbers_in(a.body)] == [
            n.replace(",", ".") for n in numbers_in(b.body)
        ]


def test_player_focus_and_favourite_club(orch, match):
    scorer = next(e.player_id for e in match.events if e.type == "shot" and e.outcome == "goal")
    side = orch.state.side_of(scorer)
    cues = orch.personalize(Viewer(mode="player_focus", club=side, player_id=scorer))
    assert any(pc.for_you for pc in cues)
    assert all(pc.kind in ("goal", "state_shift") or pc.for_you for pc in cues)


def test_personalizer_withholds_a_cue_whose_claims_fail(orch):
    cue = next(c for c in orch.cues if c.kind == "goal")
    bad = cue.model_copy(
        update={
            "claims": [cue.claims[0].model_copy(update={"value": cue.claims[0].value + 5})]
            + cue.claims[1:]
        }
    )
    p = Personalizer(verifier=Verifier())
    assert p.run(orch.state, bad, Viewer()) is None
    assert p.stats.personalized_rejected == 1


# ---------------------------------------------------------------- recap
def test_recap_is_verified_and_lists_moments(orch):
    r = orch.recap
    assert r.moments and len(r.moments) <= 3
    assert Verifier.unsupported_numbers(f"{r.headline} {r.summary}", r.claims, "en") == []
    ids = {eid for m in r.moments for eid in m.evidence_event_ids}
    assert ids and ids <= set(orch.state.events)


@pytest.mark.parametrize("lang", ["en", "es", "ca"])
def test_personal_recap_is_verified(orch, lang):
    r = orch.recap_for(Viewer(mode="fan", lang=lang))
    assert (r.score_home, r.score_away) == (orch.state.score["home"], orch.state.score["away"])
    assert Verifier.unsupported_numbers(f"{r.headline} {r.summary}", r.claims, lang) == []


def test_recap_names_whose_xg_is_whose(orch):
    summary = orch.recap.summary
    assert orch.state.team_name("home") in summary and orch.state.team_name("away") in summary


def test_recap_writer_needs_a_finished_match(match):
    bb = Blackboard(match.meta)
    with pytest.raises(AssertionError):
        RecapWriter().run(bb, [])


# ---------------------------------------------------------------- orchestrator
def test_streaming_bus_has_every_stage(orch):
    kinds = {b["type"] for b in orch.bus}
    assert {"event", "pulse", "verdict", "insight", "cue", "recap", "trust"} <= kinds


def test_truth_score_is_live(orch):
    trust = [b for b in orch.bus if b["type"] == "trust"]
    assert len(trust) > 5 and trust[-1]["data"]["truth_score"] >= 0.95


def test_whole_match_runs_fast(match):
    started = time.perf_counter()
    o = Orchestrator(match.meta)
    for ev in match.events:
        o.ingest(ev)
    o.finish()
    assert time.perf_counter() - started < 10

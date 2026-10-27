"""The Microsoft Agent Framework engine gives exactly the same results as the inline loop."""

import pytest

pytest.importorskip("agent_framework")

from whyitmatters.agents.orchestrator import Orchestrator, run_match  # noqa: E402
from whyitmatters.agents.workflow import build_workflow  # noqa: E402
from whyitmatters.simulator import simulate  # noqa: E402


@pytest.mark.parametrize("faults", [0.0, 0.3])
def test_agent_framework_engine_matches_the_inline_loop(faults):
    m = simulate(11)
    inline = run_match(m, fault_rate=faults, seed=11)
    maf = run_match(m, fault_rate=faults, seed=11, engine="agent_framework")
    assert [c.model_dump() for c in maf.cues] == [c.model_dump() for c in inline.cues]
    a, b = inline.trust(), maf.trust()
    for key in ("truth_score", "claims_generated", "retries", "dropped", "insights", "cues"):
        assert a[key] == b[key], key
    assert b["engine"] == "agent_framework"
    assert maf.workflow.runs == len(m.events) + 1  # one graph run per event, plus full time


@pytest.mark.parametrize("seed", range(5))
def test_parity_on_seeds_0_to_4(seed):
    """Identical cues, verdict stream and insights on the inline and Agent Framework engines."""
    m = simulate(seed)
    inline = run_match(m, fault_rate=0.3, seed=seed)
    maf = run_match(m, fault_rate=0.3, seed=seed, engine="agent_framework")

    def strip(bus):
        return [
            {**r, "data": {k: v for k, v in r["data"].items() if k != "latency_ms"}}
            for r in bus
            if r["type"] != "trust"
        ]

    assert strip(maf.bus) == strip(inline.bus)
    assert [i.id for i in maf.insights] == [i.id for i in inline.insights]
    assert [c.model_dump() for c in maf.cues] == [c.model_dump() for c in inline.cues]
    a, b = inline.trust(audit=True), maf.trust(audit=True)
    assert (a["truth_score"], a["on_air_accuracy"]) == (b["truth_score"], b["on_air_accuracy"])


def test_the_personalizer_node_renders_for_live_viewers():
    from whyitmatters.agents.models import Viewer

    m = simulate(3)
    viewer = Viewer(mode="fan", lang="es")
    orch = Orchestrator(m.meta, engine="agent_framework")
    orch.live_viewers.append(viewer)
    for ev in m.events:
        orch.ingest(ev)
    live = [pc.model_dump() for pc in orch.live_personal]
    assert live and live == [pc.model_dump() for pc in orch.personalize(viewer)]


def test_the_verifier_routes_every_draft():
    """The graph: watcher -> explainer -> verifier, ok -> producer -> personalizer, retry ->
    explainer, give up -> drop, and the next candidate goes back to the explainer."""
    wf = build_workflow(Orchestrator(simulate(1).meta))
    edges = {
        (e.source_id, e.target_id)
        for g in wf.edge_groups
        for e in g.edges
        if not e.source_id.startswith("internal:")  # the framework's own self-edges
    }
    assert edges == {
        ("tactics_watcher", "explainer"),
        ("explainer", "verifier"),
        ("verifier", "producer"),
        ("verifier", "explainer"),
        ("verifier", "drop"),
        ("producer", "personalizer"),
        ("personalizer", "explainer"),
        ("drop", "explainer"),
    }

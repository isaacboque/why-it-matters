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
    assert maf.workflow.runs == len(maf.insights) + b["dropped"]


def test_the_verifier_routes_every_draft():
    """Edges: explainer -> verifier, then ok -> publisher, retry -> explainer, give up -> drop."""
    wf = build_workflow(Orchestrator(simulate(1).meta))
    edges = {
        (e.source_id, e.target_id)
        for g in wf.edge_groups
        for e in g.edges
        if not e.source_id.startswith("internal:")  # the framework's own self-edges
    }
    assert edges == {
        ("explainer", "verifier"),
        ("verifier", "publisher"),
        ("verifier", "explainer"),
        ("verifier", "drop"),
    }

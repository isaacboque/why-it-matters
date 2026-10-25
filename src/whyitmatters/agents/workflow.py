"""The insight pipeline as a Microsoft Agent Framework workflow.

    Explainer ──draft──▶ Verifier ──ok──────────────▶ Publisher (Producer decides what airs)
        ▲                    │
        └──── rejected, ─────┤
              retry          └──rejected 3 times──▶ Drop

Each box is an Agent Framework `Executor` wrapping the same agent the inline loop uses, and
the routing is conditional edges, so the Verifier's verdict, not the writer, decides whether a
draft is retried, published or dropped. The agents share state through the Blackboard (match
state, raw event log) and hand off typed messages (`Attempt`, `Checked`).

Install with `pip install -e ".[maf]"`; run with `WIM_ENGINE=agent_framework`. Results are
identical to the inline engine (tests/test_workflow.py).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from whyitmatters.agents.models import Draft, InsightCandidate, Verdict

if TYPE_CHECKING:
    from whyitmatters.agents.orchestrator import Orchestrator

MAX_ATTEMPTS = 3


@dataclass
class Attempt:
    """Explainer's input: write (or rewrite) this candidate."""

    cand: InsightCandidate
    attempt: int
    started: float
    previous: Verdict | None = None


@dataclass
class Drafted:
    """Explainer -> Verifier handoff."""

    cand: InsightCandidate
    attempt: int
    started: float
    draft: Draft


@dataclass
class Checked:
    """Verifier's output, routed by its verdict."""

    cand: InsightCandidate
    attempt: int
    started: float
    draft: Draft
    verdict: Verdict


class ExplainerExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="explainer")
        self.orch = orch

    @handler
    async def write(self, msg: Attempt, ctx: WorkflowContext[Drafted]) -> None:
        draft = self.orch.explainer.run(self.orch.state, msg.cand, msg.attempt, msg.previous)
        await ctx.send_message(Drafted(msg.cand, msg.attempt, msg.started, draft))

    @handler
    async def rewrite(self, msg: Checked, ctx: WorkflowContext[Drafted]) -> None:
        """A rejected draft comes back with the Verifier's reasons."""
        attempt = msg.attempt + 1
        draft = self.orch.explainer.run(self.orch.state, msg.cand, attempt, msg.verdict)
        await ctx.send_message(Drafted(msg.cand, attempt, msg.started, draft))


class VerifierExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="verifier")
        self.orch = orch

    @handler
    async def check(self, msg: Drafted, ctx: WorkflowContext[Checked]) -> None:
        verdict = self.orch.verifier.run(self.orch.state, msg.draft)
        self.orch.on_verdict(msg.cand, msg.attempt, msg.draft, verdict)
        await ctx.send_message(Checked(msg.cand, msg.attempt, msg.started, msg.draft, verdict))


class PublisherExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="publisher")
        self.orch = orch

    @handler
    async def publish(self, msg: Checked, ctx: WorkflowContext[Any, str]) -> None:
        insight = self.orch.publish(msg.cand, msg.draft, msg.attempt, msg.started)
        await ctx.yield_output(insight.id)


class DropExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="drop")
        self.orch = orch

    @handler
    async def drop(self, msg: Checked, ctx: WorkflowContext[Any, str]) -> None:
        self.orch.drop(msg.cand)
        await ctx.yield_output("")


def _ok(msg: Any) -> bool:
    return isinstance(msg, Checked) and msg.verdict.ok


def _retry(msg: Any) -> bool:
    return isinstance(msg, Checked) and not msg.verdict.ok and msg.attempt < MAX_ATTEMPTS


def _give_up(msg: Any) -> bool:
    return isinstance(msg, Checked) and not msg.verdict.ok and msg.attempt >= MAX_ATTEMPTS


def build_workflow(orch: Orchestrator):
    explainer = ExplainerExecutor(orch)
    verifier = VerifierExecutor(orch)
    publisher = PublisherExecutor(orch)
    dropper = DropExecutor(orch)
    return (
        WorkflowBuilder(
            name="whyitmatters-insight",
            description="Draft, verify against the raw event log, retry or publish.",
            start_executor=explainer,
        )
        .add_edge(explainer, verifier)
        .add_edge(verifier, publisher, condition=_ok)
        .add_edge(verifier, explainer, condition=_retry)
        .add_edge(verifier, dropper, condition=_give_up)
        .build()
    )


def _run_sync(coro):
    """Run a coroutine from sync code, also when this thread already has an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class InsightWorkflow:
    """One workflow run per insight candidate, on the orchestrator's shared state."""

    def __init__(self, orch: Orchestrator):
        self.orch = orch
        self.runs = 0

    def explain(self, cand: InsightCandidate) -> None:
        workflow = build_workflow(self.orch)  # workflows are single-run objects
        _run_sync(workflow.run(Attempt(cand, 1, time.perf_counter())))
        self.runs += 1

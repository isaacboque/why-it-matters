"""The whole insight pipeline as a Microsoft Agent Framework workflow.

    TacticsWatcher ─candidates─▶ Explainer ─draft─▶ Verifier ─ok─▶ Producer ─▶ Personalizer
                                    ▲                  │         (on-air       (viewers)
                                    └── rejected, ─────┤          budget)           │
                                        retry          └─rejected 3 times─▶ Drop    │
                                    ▲                                         │     │
                                    └──────────── next candidate ─────────────┴─────┘

Each box is an Agent Framework `Executor` wrapping the same agent the inline loop uses, and
the routing is conditional edges, so the Verifier's verdict, not the writer, decides whether a
draft is retried, aired or dropped. The agents share state through the Blackboard (match
state, raw event log) and hand off typed messages (`Batch`, `Drafted`, `Checked`, `Aired`).

One workflow run handles one event: the TacticsWatcher picks the moments worth explaining and
the candidates go through the loop one at a time (the Producer's budget and the order of the
bus depend on that), the Personalizer or Drop handing the next one back to the Explainer.

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

from whyitmatters.agents.models import Cue, Draft, Insight, InsightCandidate, Verdict
from whyitmatters.schema import Event

if TYPE_CHECKING:
    from whyitmatters.agents.orchestrator import Orchestrator

MAX_ATTEMPTS = 3


@dataclass
class EventIn:
    """The workflow's input: one match event and what the Match Pulse produced for it."""

    ev: Event
    pulse_out: list
    analyse_event: bool


@dataclass
class Batch:
    """The candidates still to explain for this event, handled in order."""

    queue: tuple[InsightCandidate, ...]


@dataclass
class Drafted:
    """Explainer -> Verifier handoff."""

    cand: InsightCandidate
    attempt: int
    started: float
    draft: Draft
    rest: tuple[InsightCandidate, ...]


@dataclass
class Checked:
    """Verifier's output, routed by its verdict."""

    cand: InsightCandidate
    attempt: int
    started: float
    draft: Draft
    verdict: Verdict
    rest: tuple[InsightCandidate, ...]


@dataclass
class Aired:
    """Producer -> Personalizer: the insight and the cue it became, if the budget allowed one."""

    insight: Insight
    cue: Cue | None
    rest: tuple[InsightCandidate, ...]


class TacticsWatcherExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="tactics_watcher")
        self.orch = orch

    @handler
    async def watch(self, msg: EventIn, ctx: WorkflowContext[Batch]) -> None:
        cands = self.orch.watch(msg.ev, msg.pulse_out, msg.analyse_event)
        if cands:
            await ctx.send_message(Batch(tuple(cands)))


class ExplainerExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="explainer")
        self.orch = orch

    @handler
    async def write(self, msg: Batch, ctx: WorkflowContext[Drafted]) -> None:
        """First draft of the next candidate in the queue."""
        cand, rest = msg.queue[0], msg.queue[1:]
        started = time.perf_counter()
        draft = self.orch.explainer.run(self.orch.state, cand, 1, None)
        await ctx.send_message(Drafted(cand, 1, started, draft, rest))

    @handler
    async def rewrite(self, msg: Checked, ctx: WorkflowContext[Drafted]) -> None:
        """A rejected draft comes back with the Verifier's reasons."""
        attempt = msg.attempt + 1
        draft = self.orch.explainer.run(self.orch.state, msg.cand, attempt, msg.verdict)
        await ctx.send_message(Drafted(msg.cand, attempt, msg.started, draft, msg.rest))


class VerifierExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="verifier")
        self.orch = orch

    @handler
    async def check(self, msg: Drafted, ctx: WorkflowContext[Checked]) -> None:
        verdict = self.orch.verifier.run(self.orch.state, msg.draft)
        self.orch.on_verdict(msg.cand, msg.attempt, msg.draft, verdict)
        await ctx.send_message(
            Checked(msg.cand, msg.attempt, msg.started, msg.draft, verdict, msg.rest)
        )


class ProducerExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="producer")
        self.orch = orch

    @handler
    async def air(self, msg: Checked, ctx: WorkflowContext[Aired]) -> None:
        cues_before = len(self.orch.cues)
        insight = self.orch.publish(msg.cand, msg.draft, msg.attempt, msg.started)
        cue = self.orch.cues[-1] if len(self.orch.cues) > cues_before else None
        await ctx.send_message(Aired(insight, cue, msg.rest))


class PersonalizerExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="personalizer")
        self.orch = orch

    @handler
    async def personalize(self, msg: Aired, ctx: WorkflowContext[Batch, str]) -> None:
        """Re-render an aired cue for every viewer watching live (none unless registered)."""
        if msg.cue is not None:
            for viewer in self.orch.live_viewers:
                pc = self.orch.personalizer.run(self.orch.state, msg.cue, viewer)
                if pc is not None:
                    self.orch.live_personal.append(pc)
        await ctx.yield_output(msg.insight.id)
        if msg.rest:
            await ctx.send_message(Batch(msg.rest))


class DropExecutor(Executor):
    def __init__(self, orch: Orchestrator):
        super().__init__(id="drop")
        self.orch = orch

    @handler
    async def drop(self, msg: Checked, ctx: WorkflowContext[Batch, str]) -> None:
        self.orch.drop(msg.cand)
        await ctx.yield_output("")
        if msg.rest:
            await ctx.send_message(Batch(msg.rest))


def _ok(msg: Any) -> bool:
    return isinstance(msg, Checked) and msg.verdict.ok


def _retry(msg: Any) -> bool:
    return isinstance(msg, Checked) and not msg.verdict.ok and msg.attempt < MAX_ATTEMPTS


def _give_up(msg: Any) -> bool:
    return isinstance(msg, Checked) and not msg.verdict.ok and msg.attempt >= MAX_ATTEMPTS


def _next(msg: Any) -> bool:
    return isinstance(msg, Batch)


def build_workflow(orch: Orchestrator):
    watcher = TacticsWatcherExecutor(orch)
    explainer = ExplainerExecutor(orch)
    verifier = VerifierExecutor(orch)
    producer = ProducerExecutor(orch)
    personalizer = PersonalizerExecutor(orch)
    dropper = DropExecutor(orch)
    return (
        WorkflowBuilder(
            name="whyitmatters-insight",
            description="Watch, draft, verify against the raw log, retry or air, personalize.",
            start_executor=watcher,
        )
        .add_edge(watcher, explainer)
        .add_edge(explainer, verifier)
        .add_edge(verifier, producer, condition=_ok)
        .add_edge(verifier, explainer, condition=_retry)
        .add_edge(verifier, dropper, condition=_give_up)
        .add_edge(producer, personalizer)
        .add_edge(personalizer, explainer, condition=_next)
        .add_edge(dropper, explainer, condition=_next)
        .build()
    )


class InsightWorkflow:
    """One workflow run per match event, on the orchestrator's shared state."""

    def __init__(self, orch: Orchestrator):
        self.orch = orch
        self.runs = 0
        self.graph = build_workflow(orch)  # reused: each run starts from a clean slate
        self._loop = asyncio.new_event_loop()  # one loop for the whole match, not one per event

    def process(self, ev: Event, pulse_out: list, analyse_event: bool = True) -> None:
        coro = self.graph.run(EventIn(ev, pulse_out, analyse_event))
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._loop.run_until_complete(coro)
        else:  # called from async code (the API's event loop): use a worker thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self._loop.run_until_complete, coro).result()
        self.runs += 1

    def __del__(self):
        try:
            self._loop.close()
        except Exception:  # noqa: BLE001
            pass

"""Orchestrator: streams a match through the agent team and records every handoff.

Flow per event:  Blackboard.ingest -> Analyst -> (Explainer <-> Verifier, up to
MAX_ATTEMPTS) -> Producer -> cue.  At full time: RecapWriter, verified like any insight.

Every step is appended to `self.bus` as a typed record, which is what the API streams to
the studio and what the trust panel counts.
"""

from __future__ import annotations

import time
from typing import Any

from whyitmatters.agents.analyst import Analyst
from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.explainer import Explainer
from whyitmatters.agents.generator import TemplateGenerator, TextGenerator
from whyitmatters.agents.models import Cue, Insight, PersonalCue, Recap, TrustStats, Viewer
from whyitmatters.agents.personalizer import Personalizer
from whyitmatters.agents.producer import Producer
from whyitmatters.agents.recap import RecapWriter
from whyitmatters.agents.verifier import Verifier
from whyitmatters.pulse import PulseSnapshot, Transition
from whyitmatters.schema import Event, Match, MatchMeta

MAX_ATTEMPTS = 3  # first draft + 2 retries


class Orchestrator:
    def __init__(
        self,
        meta: MatchMeta,
        generator: TextGenerator | None = None,
        fault_rate: float = 0.0,
        seed: int = 0,
        budget: int = 3,
    ):
        gen = generator or TemplateGenerator()
        self.state = Blackboard(meta)
        self.stats = TrustStats()
        self.analyst = Analyst()
        self.explainer = Explainer(gen, fault_rate=fault_rate, seed=seed)
        self.verifier = Verifier()
        self.producer = Producer(budget=budget)
        self.personalizer = Personalizer(gen, self.verifier, self.stats)
        self.recap_writer = RecapWriter(gen, self.verifier)
        self.bus: list[dict[str, Any]] = []
        self.insights: list[Insight] = []
        self.cues: list[Cue] = []
        self.recap: Recap | None = None
        self.latencies_ms: list[float] = []

    def _emit(self, kind: str, t: float, data: Any) -> None:
        payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
        self.bus.append({"type": kind, "t": round(t, 1), "data": payload})

    # ------------------------------------------------------------------ streaming
    def ingest(self, ev: Event) -> None:
        pulse_out = self.state.ingest(ev)
        self._handle(ev, pulse_out)

    def finish(self) -> Recap:
        last = self.state.last_event
        assert last is not None
        self._handle(last, self.state.finish(), analyse_event=False)
        recap = self.recap_writer.run(self.state, self.cues)
        checks = self.verifier.check_claims(self.state, recap.claims)
        unsupported = self.verifier.unsupported_numbers(
            f"{recap.headline} {recap.summary}", recap.claims, "en")
        self._count(checks)
        if unsupported or not all(c.ok for c in checks):
            raise RuntimeError(f"recap failed verification: {unsupported or checks}")
        self.recap = recap
        self._emit("recap", last.t, recap)
        self._emit("trust", last.t, self.stats.as_dict())
        return recap

    def _handle(self, ev: Event, pulse_out: list, analyse_event: bool = True) -> None:
        for item in pulse_out:
            if isinstance(item, PulseSnapshot):
                self._emit("pulse", (item.minute + 1) * 60.0, {
                    "minute": item.minute, "dominance": item.dominance, "chaos": item.chaos,
                    "state": item.state, "raw_state": item.raw_state,
                    "home": item.window.home.model_dump(), "away": item.window.away.model_dump(),
                    "turnovers_per_min": item.window.turnovers_per_min,
                })
            elif isinstance(item, Transition):
                self._emit("transition", (item.detected_minute + 1) * 60.0, {
                    "id": item.id, "minute": item.detected_minute,
                    "estimated_minute": item.estimated_minute,
                    "from": item.from_state, "to": item.to_state, "evidence": item.evidence,
                })
        if analyse_event:
            self._emit("event", ev.t, ev.model_dump(mode="json", exclude_none=True))
        candidates = self.analyst.run(self.state, ev, pulse_out if analyse_event else
                                      [p for p in pulse_out if isinstance(p, Transition)])
        if not analyse_event:
            candidates = [c for c in candidates if c.kind == "state_shift"]
        for cand in candidates:
            self._explain(cand)

    def _count(self, checks) -> None:
        self.stats.claims_generated += len(checks)
        self.stats.claims_verified += sum(c.ok for c in checks)

    def _explain(self, cand) -> None:
        started = time.perf_counter()
        verdict = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            draft = self.explainer.run(self.state, cand, attempt, verdict)
            verdict = self.verifier.run(self.state, draft)
            self._count(verdict.checks)
            if attempt == 1:
                self.stats.first_drafts += 1
                self.stats.first_drafts_ok += verdict.ok
            else:
                self.stats.retries += 1
            self._emit("verdict", cand.t, {
                "candidate_id": cand.id, "kind": cand.kind, "attempt": attempt,
                "ok": verdict.ok, "headline": draft.headline,
                "failures": [c.reason for c in verdict.failures],
                "unsupported_numbers": verdict.unsupported_numbers,
            })
            if verdict.ok:
                latency = (time.perf_counter() - started) * 1000
                self.latencies_ms.append(latency)
                insight = Insight(
                    id=cand.id, kind=cand.kind, minute=cand.minute, t=cand.t,
                    significance=cand.significance, side=cand.side, player_id=cand.player_id,
                    headline=draft.headline, body=draft.body, claims=draft.claims,
                    slots=draft.slots, evidence=cand.evidence, attempts=attempt,
                    latency_ms=round(latency, 3),
                )
                self.insights.append(insight)
                self._emit("insight", cand.t, insight)
                cue = self.producer.run(insight)
                if cue is not None:
                    self.cues.append(cue)
                    self._emit("cue", cue.t_in, cue)
                return
        self.stats.dropped += 1
        self._emit("dropped", cand.t, {"candidate_id": cand.id, "kind": cand.kind})

    # ------------------------------------------------------------------ viewers
    def personalize(self, viewer: Viewer) -> list[PersonalCue]:
        out = []
        for cue in self.cues:
            pc = self.personalizer.run(self.state, cue, viewer)
            if pc is not None:
                out.append(pc)
        return out

    def recap_for(self, viewer: Viewer) -> Recap:
        return self.recap_writer.run(
            self.state, self.cues, viewer.mode, viewer.lang,
            personalize=lambda c: self.personalizer.run(self.state, c, viewer),
        )


def run_match(match: Match, **kw) -> Orchestrator:
    orch = Orchestrator(match.meta, **kw)
    for ev in match.events:
        orch.ingest(ev)
    orch.finish()
    return orch

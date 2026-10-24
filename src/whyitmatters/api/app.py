"""WhyItMatters API: replays a synthetic match through the agent team as a live feed.

    GET /health                       liveness
    GET /matches/{seed}               teams and players (for selectors)
    GET /matches/{seed}/stream        Server-Sent Events replay of the whole match
    GET /matches/{seed}/cues          overlay cue JSON for a graphics partner
    GET /matches/{seed}/personal      the same cues as one viewer sees them, plus the recap
    GET /eval                         detection quality vs ground truth (the trust panel)

Everything is computed offline from the seed; the stream only paces what is already
decided, so a reconnect always shows the same match.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as ApiPath
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from whyitmatters import __version__
from whyitmatters.agents import Orchestrator, run_match
from whyitmatters.agents.models import Cue, Lang, Mode, PersonalCue, Recap, Viewer
from whyitmatters.eval import score_match, summarize
from whyitmatters.eval.__main__ import EVAL_SEED_OFFSET
from whyitmatters.schema import Match, MatchMeta, Side
from whyitmatters.simulator import simulate

DEFAULT_DURATION_S = 180.0  # a 90-minute match replays in about three minutes
MAX_SEED = 100_000
EVENT_FIELDS = (
    "id",
    "t",
    "period",
    "minute",
    "type",
    "side",
    "player_id",
    "x",
    "y",
    "end_x",
    "end_y",
    "outcome",
    "xg",
    "score_home",
    "score_away",
)

SeedPath = Annotated[int, ApiPath(ge=0, le=MAX_SEED, description="Match seed")]


# ------------------------------------------------------------------------ response models
class Health(BaseModel):
    status: str
    version: str


class CuesResponse(BaseModel):
    """Overlay feed: every cue the Producer put on air, with the proof behind it."""

    match_id: str
    seed: int
    cues: list[Cue]
    trust: dict[str, float]


class PersonalResponse(BaseModel):
    viewer: Viewer
    cues: list[PersonalCue]
    recap: Recap


class EvalResponse(BaseModel):
    matches: int
    precision: float
    recall: float
    minute_accuracy: float
    timeline_accuracy: float
    mean_detection_lag_min: float


# ------------------------------------------------------------------------ match cache
@lru_cache(maxsize=24)
def _run(seed: int, faults: float) -> tuple[Match, Orchestrator]:
    match = simulate(seed)
    return match, run_match(match, fault_rate=faults, seed=seed)


def _load(seed: int, faults: float) -> tuple[Match, Orchestrator]:
    return _run(seed, round(faults, 2))


@lru_cache(maxsize=4)
def _eval(seeds: int) -> dict[str, float]:
    scores = [score_match(simulate(EVAL_SEED_OFFSET + i)) for i in range(seeds)]
    return summarize(scores).as_dict()


# ------------------------------------------------------------------------ stream feed
def _compact(ev: dict[str, Any]) -> dict[str, Any]:
    return {k: ev[k] for k in EVENT_FIELDS if k in ev}


def _why(orch: Orchestrator, cue: Cue) -> dict[str, Any]:
    """Everything the studio's 'Why?' drawer shows for one cue."""
    insight = next((i for i in orch.insights if i.id == cue.insight_id), None)
    checks = orch.verifier.check_claims(orch.state, cue.claims)
    history = [
        {
            "attempt": b["data"]["attempt"],
            "ok": b["data"]["ok"],
            "failures": b["data"]["failures"],
            "unsupported_numbers": b["data"]["unsupported_numbers"],
        }
        for b in orch.bus
        if b["type"] == "verdict" and b["data"]["candidate_id"] == cue.insight_id
    ]
    evidence = []
    for eid in cue.evidence_event_ids[:6]:
        ev = orch.state.events.get(eid)
        if ev is not None:
            row = _compact(ev.model_dump(mode="json", exclude_none=True))
            row["player"] = orch.state.player_name(ev.player_id)
            evidence.append(row)
    return {
        "claims": [c.model_dump(mode="json") for c in checks],
        "verified": all(c.ok for c in checks),
        "attempts": insight.attempts if insight else 1,
        "latency_ms": insight.latency_ms if insight else 0.0,
        "history": history,
        "evidence": evidence,
    }


def build_feed(orch: Orchestrator) -> list[dict[str, Any]]:
    """The orchestrator's bus as studio-ready records, in match-clock order."""
    cues = {c.cue_id: c for c in orch.cues}
    feed = [{"type": "meta", "t": 0.0, "data": orch.state.meta.model_dump(mode="json")}]
    for b in orch.bus:
        data = b["data"]
        if b["type"] == "event":
            data = _compact(data)
        elif b["type"] == "cue":
            data = {**data, "why": _why(orch, cues[data["cue_id"]])}
        feed.append({"type": b["type"], "t": b["t"], "data": data})
    feed.sort(key=lambda r: r["t"])  # stable: ties keep processing order
    return feed


def _sse(kind: str, data: Any) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def _replay(feed: list[dict[str, Any]], duration: float) -> AsyncIterator[str]:
    total = max((r["t"] for r in feed), default=0.0) or 1.0
    speed = total / duration if duration > 0 else 0.0  # match seconds per real second
    started = time.monotonic()
    for i, rec in enumerate(feed):
        if speed:
            wait = started + rec["t"] / speed - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
        elif i % 200 == 0:
            await asyncio.sleep(0)
        yield _sse(rec["type"], {"t": rec["t"], "data": rec["data"]})
    yield _sse("end", {"t": total})


# ------------------------------------------------------------------------ app
def create_app() -> FastAPI:
    app = FastAPI(
        title="WhyItMatters",
        version=__version__,
        description="Explainable, verified match intelligence from synthetic football events.",
    )

    @app.get("/health", response_model=Health, tags=["system"])
    def health() -> Health:
        return Health(status="ok", version=__version__)

    @app.get("/matches/{seed}", response_model=MatchMeta, tags=["match"])
    def match_info(seed: SeedPath) -> MatchMeta:
        return _load(seed, 0.0)[0].meta

    @app.get("/matches/{seed}/stream", tags=["match"], response_class=StreamingResponse)
    async def stream(
        seed: SeedPath,
        duration: float = Query(
            DEFAULT_DURATION_S,
            ge=0,
            le=3600,
            description="Real seconds the whole match takes to replay; 0 = as fast as possible",
        ),
        faults: float = Query(
            0.0,
            ge=0,
            le=1,
            description="Share of first drafts a simulated unreliable model mis-states",
        ),
    ) -> StreamingResponse:
        """Server-Sent Events. Event types: meta, event, pulse, transition, verdict, insight,
        cue (with `why`), dropped, trust, recap, end. Every message is `{"t", "data"}`."""
        _, orch = _load(seed, faults)
        return StreamingResponse(
            _replay(build_feed(orch), duration),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/matches/{seed}/cues", response_model=CuesResponse, tags=["match"])
    def cues(
        seed: SeedPath,
        faults: float = Query(0.0, ge=0, le=1),
    ) -> CuesResponse:
        """Overlay cues as JSON: `t_in`/`t_out` in match seconds, `priority` 1 = highest,
        the claims behind every number and the event ids that prove them."""
        match, orch = _load(seed, faults)
        return CuesResponse(
            match_id=match.meta.match_id,
            seed=seed,
            cues=orch.cues,
            trust=orch.trust(audit=True),
        )

    @app.get("/matches/{seed}/personal", response_model=PersonalResponse, tags=["match"])
    def personal(
        seed: SeedPath,
        mode: Mode = "fan",
        lang: Lang = "en",
        club: Side | None = None,
        player: str | None = None,
        faults: float = Query(0.0, ge=0, le=1),
    ) -> PersonalResponse:
        """Cues and recap as one viewer sees them. Numbers are re-verified per viewer."""
        _, orch = _load(seed, faults)
        if player is not None and player not in orch.state.players:
            raise HTTPException(status_code=422, detail=f"unknown player {player!r}")
        viewer = Viewer(mode=mode, lang=lang, club=club, player_id=player)
        return PersonalResponse(
            viewer=viewer, cues=orch.personalize(viewer), recap=orch.recap_for(viewer)
        )

    @app.get("/eval", response_model=EvalResponse, tags=["system"])
    def evaluation(seeds: int = Query(20, ge=1, le=40)) -> dict[str, float]:
        """Phase-shift detection vs the simulator's planted ground truth (held-out seeds)."""
        return _eval(seeds)

    web = Path(os.environ.get("WHYITMATTERS_WEB", Path(__file__).resolve().parents[3] / "web"))
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()

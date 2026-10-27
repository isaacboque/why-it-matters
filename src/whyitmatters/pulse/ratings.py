"""Player cards and a transparent 1-10 rating.

Everything is summed from the raw event log (and its freeze frames), per player, so every
figure can be recomputed. The rating is a plain sum of visible parts, not a model:

    rating = 5.2 + xT + defence + creation + finishing - losses        (clipped to 1..10)

    xT         3.0 per unit of Expected Threat added by the player's completed passes and carries
    defence    0.08 per ball won (tackle won or interception)
    creation   0.25 per key pass (the pass that found a shooter) + 2.0 per unit of xG it created
    finishing  0.8 per goal + 1.0 per unit of xG the player's own shots were worth
    losses     0.03 per incomplete pass + 0.10 per lost tackle

The weights were set on simulator seeds 0-19 so a typical outfield player lands near 6 and the
best player of a match near 8; they are a stated convention, not an external benchmark.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from whyitmatters.pulse import chances, damage
from whyitmatters.pulse import xt as xt_model
from whyitmatters.pulse.metrics import (
    FINAL_THIRD_X,
    PROGRESSIVE_M,
    duel_winner,
    is_recovery,
)
from whyitmatters.pulse.physical import SPRINT_KMH, Checkpoints
from whyitmatters.schema import Event, EventType, MatchMeta, Outcome

BASE = 5.2
W_XT = 3.0
W_WIN = 0.08
W_KEY = 0.25
W_XA = 2.0
W_GOAL = 0.8
W_XG = 1.0
W_INCOMPLETE = 0.03
W_LOST_DUEL = 0.10
LOW, HIGH = 1.0, 10.0

COMPONENTS = ("xt", "defence", "creation", "finishing", "losses")


def _blank() -> dict[str, float]:
    return defaultdict(float)  # type: ignore[return-value]


def player_cards(meta: MatchMeta, events: list[Event]) -> list[dict[str, Any]]:
    """One card per player (both squads): counts, physical figures, rating and its breakdown."""
    stat: dict[str, dict[str, float]] = defaultdict(_blank)
    order = {"home": [p.id for p in meta.home.players], "away": [p.id for p in meta.away.players]}
    cps = Checkpoints()
    prev: Event | None = None
    for ev in events:
        for side, legs in cps.ingest(ev).items():
            for leg in legs:
                s = stat[order[side][leg.index]]
                s["distance_m"] += leg.metres
                s["sprints"] += leg.kmh >= SPRINT_KMH
                s["top_speed_kmh"] = max(s["top_speed_kmh"], leg.kmh)
        pid = ev.player_id
        if pid is not None:
            s = stat[pid]
            if ev.type == EventType.PASS:
                s["passes"] += 1
                if damage.is_completed_pass(ev):
                    s["completed"] += 1
                    s["involvement"] += 1
                    if ev.receiver_id:
                        stat[ev.receiver_id]["involvement"] += 1
                        stat[ev.receiver_id]["received"] += 1
                    s["xt"] += xt_model.added(ev.x, ev.y, ev.end_x, ev.end_y)
                    if ev.end_x - ev.x >= PROGRESSIVE_M or (ev.x < FINAL_THIRD_X <= ev.end_x):
                        s["progressive"] += 1
                    lines = damage.lines_broken(ev)
                    s["line_breaks"] += lines > 0
                    s["packing"] += damage.packing(ev)
                else:
                    s["incomplete"] += 1
            elif ev.type == EventType.CARRY and ev.end_x is not None:
                s["xt"] += xt_model.added(ev.x, ev.y, ev.end_x, ev.end_y)
                if ev.end_x - ev.x >= PROGRESSIVE_M:
                    s["progressive"] += 1
            elif ev.type == EventType.SHOT:
                s["shots"] += 1
                s["xg"] += ev.xg or 0.0
                s["goals"] += ev.outcome == Outcome.GOAL
                assist = chances.assist_of(prev, ev)
                if assist is not None and assist.player_id:
                    stat[assist.player_id]["key_passes"] += 1
                    stat[assist.player_id]["xa"] += ev.xg or 0.0
            if is_recovery(ev):
                s["wins"] += 1
            duel = duel_winner(ev)
            if duel is not None and ev.type == EventType.TACKLE and ev.outcome == Outcome.LOST:
                s["lost_duels"] += 1
            if ev.type == EventType.PRESSURE:
                s["pressures"] += 1
        prev = ev

    cards = []
    for side, team in (("home", meta.home), ("away", meta.away)):
        for p in team.players:
            s = stat[p.id]
            parts = {
                "xt": W_XT * s["xt"],
                "defence": W_WIN * s["wins"],
                "creation": W_KEY * s["key_passes"] + W_XA * s["xa"],
                "finishing": W_GOAL * s["goals"] + W_XG * s["xg"],
                "losses": -(W_INCOMPLETE * s["incomplete"] + W_LOST_DUEL * s["lost_duels"]),
            }
            rating = min(max(BASE + sum(parts.values()), LOW), HIGH)
            cards.append(
                {
                    "player_id": p.id,
                    "name": p.name,
                    "side": side,
                    "position": p.position,
                    "rating": round(rating, 1),
                    "breakdown": {k: round(v, 2) for k, v in parts.items()},
                    "involvement": int(s["involvement"]),
                    "passes": int(s["passes"]),
                    "completed": int(s["completed"]),
                    "xt": round(s["xt"], 3),
                    "progressive": int(s["progressive"]),
                    "line_breaks": int(s["line_breaks"]),
                    "key_passes": int(s["key_passes"]),
                    "xa": round(s["xa"], 2),
                    "shots": int(s["shots"]),
                    "xg": round(s["xg"], 2),
                    "goals": int(s["goals"]),
                    "wins": int(s["wins"]),
                    "lost_duels": int(s["lost_duels"]),
                    "distance_m": round(s["distance_m"]),
                    "top_speed_kmh": round(s["top_speed_kmh"], 1),
                    "sprints": int(s["sprints"]),
                }
            )
    return cards

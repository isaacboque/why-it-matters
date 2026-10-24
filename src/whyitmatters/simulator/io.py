"""JSONL match files: one `meta` line, one `event` line per event, one `truth` line last.

The line-per-event layout lets the same file be replayed as a live stream.
"""

from __future__ import annotations

import json
from pathlib import Path

from whyitmatters.schema import Event, GroundTruth, Match, MatchMeta


def write_match(match: Match, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "meta", "data": match.meta.model_dump(mode="json")}) + "\n")
        for ev in match.events:
            f.write(
                json.dumps({"kind": "event", "data": ev.model_dump(mode="json", exclude_none=True)})
                + "\n"
            )
        f.write(json.dumps({"kind": "truth", "data": match.truth.model_dump(mode="json")}) + "\n")


def read_match(path: str | Path) -> Match:
    meta = truth = None
    events: list[Event] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["kind"] == "meta":
                meta = MatchMeta.model_validate(rec["data"])
            elif rec["kind"] == "event":
                events.append(Event.model_validate(rec["data"]))
            elif rec["kind"] == "truth":
                truth = GroundTruth.model_validate(rec["data"])
    if meta is None or truth is None:
        raise ValueError(f"{path}: missing meta or truth line")
    return Match(meta=meta, events=events, truth=truth)

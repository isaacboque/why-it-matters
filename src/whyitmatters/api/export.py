"""Static demo export: the whole UI as plain files, no backend needed.

    python -m whyitmatters.api.export --seeds 7 11 23 --out dist/demo

Writes a copy of `web/` plus pre-recorded JSON per seed under `data/`. `web/app.js` switches
to static mode when it cannot reach the API (or with `?static=1`) and replays these files with
the same pacing as the live stream. Paths are relative, so any static host works.

Layout (all under `data/`):
    index.json                         manifest: seeds, focus players, every file written
    eval.json                          detection quality vs ground truth (Trust tab)
    <seed>/info.json                   teams and players (== GET /matches/{seed})
    <seed>/stream-clean.json           the full bus (== the SSE stream), model behaving
    <seed>/stream-faults.json          the same with an unreliable model (fault rate 0.3)
    <seed>/cues.json                   overlay cues + trust (== GET /matches/{seed}/cues)
    <seed>/personal-<mode>-<lang>.json analyst and fan views, every language
    <seed>/personal-player_focus-<player>-<lang>.json  for the 3 players with most cues

Favourite club is applied in the browser from each cue's `side`, so it needs no extra files.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from whyitmatters.agents import Orchestrator, run_match
from whyitmatters.agents.models import Lang, Mode, Viewer
from whyitmatters.api.app import _eval, build_feed
from whyitmatters.simulator import simulate

WEB_DIR = Path(__file__).resolve().parents[3] / "web"
FAULT_RATE = 0.3
EVAL_SEEDS = 20
FOCUS_PLAYERS = 3
LANGS: tuple[str, ...] = get_args(Lang)
MODES: tuple[str, ...] = tuple(m for m in get_args(Mode) if m != "player_focus")
SIZE_BUDGET = 5_000_000

Writer = Callable[[Path, Any], None]


def _personal(orch: Orchestrator, mode: str, lang: str, player: str | None) -> dict[str, Any]:
    """One viewer's cues + recap. Club and player highlights are applied in the browser, so each
    row carries the cue's `side` and `player_id`; claims are left out to keep the files small."""
    viewer = Viewer(mode=mode, lang=lang, player_id=player)  # type: ignore[arg-type]
    by_id = {c.cue_id: c for c in orch.cues}
    cues = []
    for pc in orch.personalize(viewer):
        row = pc.model_dump(mode="json", exclude={"claims", "evidence_event_ids"})
        row.update(side=by_id[pc.cue_id].side, player_id=by_id[pc.cue_id].player_id)
        cues.append(row)
    recap = orch.recap_for(viewer).model_dump(mode="json", exclude={"claims"})
    return {"viewer": viewer.model_dump(mode="json"), "cues": cues, "recap": recap}


def _focus_players(orch: Orchestrator) -> list[str]:
    counts = Counter(c.player_id for c in orch.cues if c.player_id)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [p for p, _ in ranked[:FOCUS_PLAYERS]]


def _export_seed(seed: int, d: Path, write: Writer) -> dict[str, Any]:
    match = simulate(seed)
    clean = run_match(match, fault_rate=0.0, seed=seed)
    faulty = run_match(match, fault_rate=FAULT_RATE, seed=seed)
    write(d / "info.json", match.meta.model_dump(mode="json"))
    write(d / "stream-clean.json", build_feed(clean))
    write(d / "stream-faults.json", build_feed(faulty))
    cues = [c.model_dump(mode="json") for c in clean.cues]
    write(
        d / "cues.json",
        {"match_id": match.meta.match_id, "seed": seed, "cues": cues, "trust": clean.trust(True)},
    )
    focus = _focus_players(clean)
    for lang in LANGS:
        for mode in MODES:
            write(d / f"personal-{mode}-{lang}.json", _personal(clean, mode, lang, None))
        for player in focus:
            name = f"personal-player_focus-{player}-{lang}.json"
            write(d / name, _personal(clean, "player_focus", lang, player))
    return {"home": match.meta.home.name, "away": match.meta.away.name, "focus_players": focus}


def export_demo(seeds: list[int], out: Path, web_dir: Path = WEB_DIR) -> dict[str, Any]:
    """Write the static demo into `out` and return the manifest (also saved as data/index.json)."""
    out = Path(out)
    shutil.copytree(web_dir, out, dirs_exist_ok=True)  # overwrites in place, never deletes
    data = out / "data"
    files: list[str] = []

    def write(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        files.append(path.relative_to(out).as_posix())

    write(data / "eval.json", _eval(EVAL_SEEDS))
    per_seed = {str(s): _export_seed(s, data / str(s), write) for s in seeds}
    manifest: dict[str, Any] = {
        "seeds": per_seed,
        "langs": list(LANGS),
        "modes": [*MODES, "player_focus"],
        "fault_rate": FAULT_RATE,
        "files": sorted([*files, "data/index.json"]),
    }
    (data / "index.json").write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    manifest["bytes"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Export a self-contained static demo")
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11, 23])
    ap.add_argument("--out", type=Path, default=Path("dist/demo"))
    args = ap.parse_args()
    m = export_demo(args.seeds, args.out)
    print(f"wrote {len(m['files'])} data files, {m['bytes'] / 1e6:.2f} MB total -> {args.out}")
    if m["bytes"] > SIZE_BUDGET:
        raise SystemExit(f"demo is {m['bytes']} bytes, over the {SIZE_BUDGET} budget")


if __name__ == "__main__":
    main()

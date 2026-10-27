"""Featured matches: score every seed for storytelling and keep the best few.

    python -m whyitmatters.simulator.featured --seeds 0-499

writes `featured.json` next to this file: a list of
`{"seed": int, "title": str, "tags": [str, ...], "home": str, "away": str}`. Titles and tags
never contain the score. Everything is deterministic (seeded simulator, seeded fault
injector, no timing in the score), so the same seeds always give the same file.

Two stages keep it fast: every seed is scored from the match itself (goals, scripted phases,
shapes, chances, club identities); only the best candidates are then run through the agent
pipeline, to score the insight mix and the Verifier rejections under injected faults.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from whyitmatters.schema import Match
from whyitmatters.simulator import simulate
from whyitmatters.simulator.teams import CLUB_IDENTITY

OUT = Path(__file__).with_name("featured.json")
COUNT = 8
SHORTLIST = 40
FAULTS = 0.3
MAX_TEAM_XG = 3.0  # a team-match above this xG, or this many goals, is implausible
MAX_GOALS = 6
IMPLAUSIBLE_PENALTY = 10.0  # larger than any story score, so such seeds fall out of the shortlist

# Tag order = priority when a match has several; the title follows the first tag it has.
TITLES = {
    "late-winner": "Late drama at {club}",
    "comeback": "Nothing is settled at {club}",
    "press-vs-patience": "Press vs patience",
    "control-vs-chaos": "Control, then chaos",
    "shape-shift": "Shape-shifters at {club}",
    "chance-fest": "Chances everywhere at {club}",
    "verifier-stress": "Caught in the act at {club}",
    "insight-mix": "A match with everything",
}


def _club(name: str) -> str:
    return name


def _goals(m: Match) -> list[tuple[float, str]]:
    return [(e.t / 60.0, e.side) for e in m.events if e.type == "shot" and e.outcome == "goal"]


def story_score(m: Match) -> tuple[float, list[str]]:
    """Stage 1: score and tags from the match and its ground truth alone."""
    tags: list[str] = []
    score = 0.0
    goals = _goals(m)
    n = len(goals)
    if 3 <= n <= 5:
        score += 1.0
    elif n in (2, 6):
        score += 0.4
    # lead changes: the story of the scoreline without its numbers
    h = a = 0
    leads: list[int] = []
    for _, side in goals:
        h += side == "home"
        a += side == "away"
        leads.append((h > a) - (h < a))
    swings = sum(1 for x, y in zip(leads, leads[1:], strict=False) if x != y and 0 not in (x, y))
    flips = sum(1 for x, y in zip([0, *leads], leads, strict=False) if x != y)
    if goals and n >= 2:
        final = leads[-1]
        before = ([0, *leads])[-2]
        if goals[-1][0] >= 80 and final != 0 and final != before:
            tags.append("late-winner")
            score += 2.0
        if swings >= 1 or (final != 0 and -final in leads):
            tags.append("comeback")
            score += 1.5 + 0.5 * swings
        score += 0.15 * flips
    kinds = [p.kind for p in m.truth.phases]
    home_c, away_c, chaos = (kinds.count(k) for k in ("home_control", "away_control", "chaos"))
    if (home_c and away_c) or chaos >= 2:
        score += 1.0 + 0.3 * min(chaos, 2)
        tags.append("control-vs-chaos")
    hi, ai = CLUB_IDENTITY[m.meta.home.short_name], CLUB_IDENTITY[m.meta.away.short_name]
    labels = {hi.label, ai.label}
    if "high-press" in labels and ("possession" in labels or "low-block" in labels):
        score += 1.2
        tags.append("press-vs-patience")
    forms = {(s.side, s.out_of_possession) for s in m.truth.shapes}
    if len({f for _, f in forms}) >= 3:
        score += 0.6
        tags.append("shape-shift")
    big = sum(k.kind == "big_chance" for k in m.truth.key_moments)
    if big >= 4:
        score += 0.25 * min(big, 8)
        tags.append("chance-fest")
    # never feature an implausible match: a team-match above 3.0 xG or a 6+ goal game
    xg = {"home": 0.0, "away": 0.0}
    for e in m.events:
        if e.type == "shot" and e.xg:
            xg[e.side] += e.xg
    if max(xg.values()) > MAX_TEAM_XG or n >= MAX_GOALS:
        score -= IMPLAUSIBLE_PENALTY
    return score, tags


def pipeline_score(m: Match) -> tuple[float, list[str]]:
    """Stage 2: insight mix on the clean run, Verifier rejections under injected faults."""
    from whyitmatters.agents import run_match

    clean = run_match(m, seed=m.meta.seed)
    kinds = {i.kind for i in clean.insights}
    tags: list[str] = []
    score = 0.2 * len(kinds)
    if len(kinds) >= 10:
        tags.append("insight-mix")
    faulty = run_match(m, fault_rate=FAULTS, seed=m.meta.seed)
    rejected = faulty.stats.retries + faulty.stats.dropped
    if rejected >= 8:
        tags.append("verifier-stress")
    score += 0.1 * min(rejected, 10)
    return score, tags


def _stage1(seed: int) -> tuple[int, float, list[str]]:
    s, t = story_score(simulate(seed))
    return seed, s, t


def _stage2(seed: int) -> tuple[int, float, list[str]]:
    m = simulate(seed)
    s, t = pipeline_score(m)
    return seed, s, t


def _pmap(fn, items, workers: int):
    if workers <= 1 or len(items) < 4:
        return [fn(i) for i in items]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items, chunksize=4))


def build(seeds: list[int], count: int = COUNT, shortlist: int = SHORTLIST, workers: int = 1):
    first = _pmap(_stage1, seeds, workers)
    first.sort(key=lambda r: (-r[1], r[0]))
    top = first[:shortlist]
    second = {r[0]: r for r in _pmap(_stage2, [r[0] for r in top], workers)}
    ranked = []
    for seed, s1, t1 in top:
        _, s2, t2 = second[seed]
        tags = list(dict.fromkeys([*t1, *t2]))
        ranked.append((s1 + s2, seed, tags))
    ranked.sort(key=lambda r: (-r[0], r[1]))

    # pick the best, but keep the set varied: one match per lead tag, one per fixture
    chosen: list[dict] = []
    used_lead: set[str] = set()
    used_fix: set[tuple[str, str]] = set()
    for pass_ in (0, 1):
        for _, seed, tags in ranked:
            if len(chosen) >= count or any(c["seed"] == seed for c in chosen):
                continue
            if not tags:
                continue
            free = [k for k in TITLES if k in tags and (pass_ == 1 or k not in used_lead)]
            if not free:
                continue
            lead = free[0]
            m = simulate(seed)
            fix = (m.meta.home.short_name, m.meta.away.short_name)
            title = TITLES[lead].format(club=_club(m.meta.home.name))
            if fix in used_fix or any(c["title"] == title for c in chosen):
                continue
            used_lead.add(lead)
            used_fix.add(fix)
            chosen.append({
                "seed": seed,
                "title": title,
                "tags": sorted(tags, key=list(TITLES).index),
                "home": m.meta.home.name,
                "away": m.meta.away.name,
            })
    chosen.sort(key=lambda c: c["seed"])
    return chosen


def parse_seeds(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Pick the featured matches")
    ap.add_argument("--seeds", default="0-499", help="e.g. 0-499 or 3,7,10-20")
    ap.add_argument("--count", type=int, default=COUNT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    feat = build(parse_seeds(args.seeds), args.count, workers=args.workers)
    text = json.dumps(feat, indent=2, ensure_ascii=False) + "\n"
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    for f in feat:
        print(f"{f['seed']:>4}  {f['title']:<38} {f['home']} v {f['away']}  {','.join(f['tags'])}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

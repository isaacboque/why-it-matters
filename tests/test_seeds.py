"""Club identities, game states, the scoreline distribution and the featured matches."""

from __future__ import annotations

import json
import statistics
from functools import cache
from pathlib import Path

import pytest

from whyitmatters.simulator import simulate
from whyitmatters.simulator.featured import build, parse_seeds, story_score
from whyitmatters.simulator.phases import NEUTRAL, game_state, style_at
from whyitmatters.simulator.teams import CLUB_IDENTITY, CLUBS

FEATURED = Path(__file__).resolve().parents[1] / "src/whyitmatters/simulator/featured.json"


@cache
def _m(seed: int):
    return simulate(seed)


@cache
def club_stats() -> dict[str, dict[str, float]]:
    """Per club over seeds 0-59: possession (pass share), long-ball share, pressures, block."""
    acc: dict[str, dict[str, list[float]]] = {}
    for seed in range(60):
        m = _m(seed)
        for side, other in (("home", "away"), ("away", "home")):
            club = getattr(m.meta, side).short_name
            mine = [e for e in m.events if e.type == "pass" and e.side == side]
            theirs = [e for e in m.events if e.type == "pass" and e.side == other]
            # Block height: mean x of the 10 outfield players while the opponent has the ball.
            # freeze.o holds the opponents in the acting team's frame, so mirror x back.
            xs = [
                105.0 - sum(p[0] for p in e.freeze.o[1:]) / 10
                for e in theirs
                if e.freeze
            ]
            a = acc.setdefault(club, {"poss": [], "long": [], "press": [], "block": []})
            a["poss"].append(len(mine) / (len(mine) + len(theirs)))
            a["long"].append(sum((e.pass_distance or 0) >= 30 for e in mine) / len(mine))
            a["press"].append(sum(e.type == "pressure" and e.side == side for e in m.events))
            a["block"].append(statistics.mean(xs))
    return {c: {k: statistics.mean(v) for k, v in d.items()} for c, d in acc.items()}


def _mean(labels: list[str], key: str) -> float:
    st = club_stats()
    return statistics.mean(
        st[c][key] for c, i in CLUB_IDENTITY.items() if i.label in labels and c in st
    )


def test_every_club_has_an_identity():
    assert {s for _, s in CLUBS} == set(CLUB_IDENTITY)
    assert {i.label for i in CLUB_IDENTITY.values()} == {
        "possession", "direct", "high-press", "low-block"}


def test_identities_measurably_differ():
    # possession clubs hold the ball more than direct clubs, and go long less
    assert _mean(["possession"], "poss") > _mean(["direct"], "poss") + 0.03
    assert _mean(["direct"], "long") > _mean(["possession"], "long") + 0.02
    # high-press clubs press more than low-block clubs (PPDA moves with it)
    assert _mean(["high-press"], "press") > 1.2 * _mean(["low-block"], "press")
    # high-press clubs defend higher than low-block clubs
    assert _mean(["high-press"], "block") > _mean(["low-block"], "block") + 2.0


def test_identity_persists_across_matches():
    st = club_stats()
    assert st["NBA"]["poss"] > st["RVM"]["poss"]
    assert st["NBA"]["poss"] > st["WHA"]["poss"]


def test_game_state_changes_behaviour():
    leader = game_state(1, 85.0)
    trailer = game_state(-1, 85.0)
    assert leader[0] < 1 < trailer[0]  # presses less / more
    assert leader[1] < 1 < trailer[1]  # less / more direct
    assert leader[3] < 0 < trailer[3]  # drops the block / pushes up
    assert game_state(1, 20.0) == game_state(0, 20.0) == (1.0, 1.0, 1.0, 0.0)  # only late on
    ph = _m(3).truth.phases
    lead = style_at(ph, 85.0, "home", 0.0, NEUTRAL, diff=1)
    trail = style_at(ph, 85.0, "home", 0.0, NEUTRAL, diff=-1)
    assert lead.line < trail.line and lead.press < trail.press


def test_scoreline_distribution_inside_audit_ranges():
    rows = []
    for seed in range(100):
        ev = _m(seed).events
        rows.append(tuple(
            sum(e.type == "shot" and e.outcome == "goal" and e.side == s for e in ev)
            for s in ("home", "away")
        ))
    n = len(rows)
    tot = [h + a for h, a in rows]
    # docs/STATS-AUDIT.md reference ranges, widened by the 100-match band used there
    assert 2.75 - 0.25 <= statistics.mean(tot) <= 3.28 + 0.25
    assert sum(t == 0 for t in tot) / n <= 0.071 + 0.04
    assert sum(t >= 6 for t in tot) / n <= 0.095 + 0.05
    assert sum(abs(h - a) >= 4 for h, a in rows) / n <= 0.10
    assert max(tot) <= 8
    assert sum(h > a for h, a in rows) > sum(h < a for h, a in rows)  # home advantage


# ---------------------------------------------------------------- featured matches
def test_featured_json_schema():
    feat = json.loads(FEATURED.read_text(encoding="utf-8"))
    assert 6 <= len(feat) <= 10
    assert len({f["seed"] for f in feat}) == len(feat)
    for f in feat:
        assert set(f) == {"seed", "title", "tags", "home", "away"}
        assert isinstance(f["seed"], int) and 0 <= f["seed"] < 100_000
        assert isinstance(f["title"], str) and 3 <= len(f["title"]) <= 48
        assert not any(ch.isdigit() for ch in f["title"])  # no score in the title
        assert f["tags"] and all(isinstance(t, str) for t in f["tags"])
        m = _m(f["seed"])
        assert (m.meta.home.name, m.meta.away.name) == (f["home"], f["away"])
        assert set(story_score(m)[1]) <= set(f["tags"])


def test_featured_is_reproducible_on_a_small_range():
    seeds = parse_seeds("0-11")
    a = build(seeds, count=3, shortlist=5)
    b = build(seeds, count=3, shortlist=5)
    assert a and a == b
    assert json.dumps(a) == json.dumps(b)
    assert all(f["seed"] in seeds for f in a)


def test_parse_seeds():
    assert parse_seeds("0-3,7,9-10") == [0, 1, 2, 3, 7, 9, 10]


@pytest.mark.parametrize("bad", ["", "a-b"])
def test_parse_seeds_rejects_junk(bad):
    with pytest.raises(ValueError):
        parse_seeds(bad)


# ---------------------------------------------------------------- goals and xG calibration
def test_featuring_penalises_implausible_matches():
    # seed 60 used to be 4.22 xG for one team; whatever the simulator does, a featured match
    # never has a team-match above 3.0 xG or a 6+ goal scoreline
    feat = json.loads(FEATURED.read_text(encoding="utf-8"))
    for f in feat:
        ev = _m(f["seed"]).events
        for side in ("home", "away"):
            assert sum(e.xg or 0 for e in ev if e.type == "shot" and e.side == side) <= 3.0
        assert sum(e.type == "shot" and e.outcome == "goal" for e in ev) < 6


def test_xg_calibration_league_like():
    xg = shots = goals = 0.0
    tm = 0
    over = 0
    for seed in range(40):
        ev = _m(seed).events
        for side in ("home", "away"):
            sh = [e for e in ev if e.type == "shot" and e.side == side]
            x = sum(e.xg for e in sh)
            xg, shots, tm, over = xg + x, shots + len(sh), tm + 1, over + (x > 3.0)
            goals += sum(e.outcome == "goal" for e in sh)
    assert 1.2 <= xg / tm <= 1.65  # team xG per match (league about 1.4 to 1.5)
    assert 0.09 <= xg / shots <= 0.125  # xG per shot
    assert over / tm <= 0.06
    assert 0.8 <= goals / xg <= 1.2  # goals track xG

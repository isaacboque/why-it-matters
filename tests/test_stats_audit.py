# ruff: noqa: E501
"""Stats audit: every number the UI and API show, recomputed from the raw event log.

The checker below is written from the metric definitions (pulse/metrics.py docstring,
docs/METHODS.md, SPEC.md) and imports nothing from `whyitmatters.pulse` (no MinuteCounter,
xt, damage or shape code). It reads only the event stream and the xT grid file. Production
output is compared with it over seeds 0-19 (the tuning seeds) and 1000-1019 (held out, the
ones `eval` uses). docs/STATS-AUDIT.md lists which test pins which metric.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from functools import cache, lru_cache
from pathlib import Path

import pytest

from whyitmatters.agents import run_match
from whyitmatters.agents.models import Viewer
from whyitmatters.api.app import build_feed
from whyitmatters.simulator import simulate

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [*range(20), *range(1000, 1020)]
GRID = json.loads((ROOT / "src/whyitmatters/pulse/xt_grid.json").read_text())["xt"]
DEFENDING = {"pressure", "tackle", "interception", "foul"}


@cache
def sim(seed: int):
    return simulate(seed)


@cache
def played(seed: int):
    match = sim(seed)
    return match, run_match(match)


def other(side: str) -> str:
    return "away" if side == "home" else "home"


# ====================================================================== independent checker
def xt_value(x: float, y: float) -> float:
    i = min(15, max(0, int(x / (105 / 16))))
    j = min(11, max(0, int(y / (68 / 12))))
    return GRID[i][j]


def lines_of(xs: list[float]) -> list[list[int]]:
    """Players grouped into lines by depth: a gap over 7.5 m starts a new line, 3 to 4 lines."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    groups = [[order[0]]]
    for a, b in zip(order, order[1:], strict=False):
        if xs[b] - xs[a] > 7.5:
            groups.append([b])
        else:
            groups[-1].append(b)

    def mean(g: list[int]) -> float:
        return sum(xs[i] for i in g) / len(g)

    while len(groups) > 4:
        gaps = [mean(groups[k + 1]) - mean(groups[k]) for k in range(len(groups) - 1)]
        k = gaps.index(min(gaps))
        groups[k : k + 2] = [groups[k] + groups[k + 1]]
    while len(groups) < 3:
        k = max(range(len(groups)), key=lambda j: len(groups[j]))
        g = sorted(groups[k], key=lambda i: xs[i])
        gaps = [xs[g[j + 1]] - xs[g[j]] for j in range(len(g) - 1)]
        if not gaps:
            break
        cut = gaps.index(max(gaps)) + 1
        groups[k : k + 1] = [g[:cut], g[cut:]]
    return groups


EDGE = [0]  # boundary comparisons decided by float noise (see span_ok)


def span_ok(y: float, lo: float, hi: float) -> bool:
    """lo <= y <= hi. Positions are 1-decimal numbers, so a pass can land exactly on a span
    edge; the product flips the frame twice (68 - (68 - y)) and may be a ulp off there. Such
    cases are counted so the comparison can allow for them."""
    if abs(y - lo) < 1e-6 or abs(y - hi) < 1e-6:
        EDGE[0] += 1
    return lo <= y <= hi


def opp_lines(ev) -> list[tuple[float, float, float]]:
    """The opponent's lines as (mean depth in the passer's x, min y, max y), back line first."""
    theirs = [105 - x for x, _ in ev.freeze.o[1:]]
    ys = [y for _, y in ev.freeze.o[1:]]
    return [
        (105 - sum(theirs[i] for i in g) / len(g), min(ys[i] for i in g), max(ys[i] for i in g))
        for g in lines_of(theirs)
    ]


def roles_broken(ev) -> list[str]:
    """Lines a completed goalward pass goes through: the segment crosses the line's depth at a
    y inside the line's span (outermost players, 2 m margin)."""
    if goal_dist(ev.end_x, ev.end_y) > 0.9 * goal_dist(ev.x, ev.y):
        return []
    lines = opp_lines(ev)
    out = []
    for i, (depth, lo, hi) in enumerate(lines):
        if not ev.x < depth < ev.end_x:
            continue
        y = ev.y + (depth - ev.x) / (ev.end_x - ev.x) * (ev.end_y - ev.y)
        if span_ok(y, lo - 2, hi + 2):
            out.append("back" if i == 0 else "forward" if i == len(lines) - 1 else "midfield")
    return out


def reception_gap(ev) -> str | None:
    """Gap between two consecutive opponent lines the pass is received in, in space."""
    if any(math.hypot(ev.end_x - ox, ev.end_y - oy) < 3 for ox, oy in ev.freeze.o):
        return None
    lines = opp_lines(ev)
    for i in range(len(lines) - 1):
        back, front = lines[i], lines[i + 1]
        if not front[0] < ev.end_x < back[0]:
            continue
        lo = min(back[1], front[1]) - 2
        hi = max(back[2], front[2]) + 2
        if not span_ok(ev.end_y, lo, hi):
            return None
        return "mid_def" if i == 0 else "fwd_mid" if i == len(lines) - 2 else "inner"
    return None


def goal_dist(x: float, y: float) -> float:
    return math.hypot(105 - x, 34 - y)


def completed(ev) -> bool:
    return ev.type == "pass" and ev.outcome == "complete" and ev.end_x is not None


def in_box(x, y):
    return x >= 88.5 and 13.84 <= y <= 54.16


def in_z14(x, y):
    return 70 <= x < 88.5 and 68 / 3 <= y < 136 / 3


def in_half_space(x, y):
    return x >= 70 and (13.84 <= y < 68 / 3 or 136 / 3 <= y <= 54.16)


COUNT_KEYS = (
    "passes complete ft_passes build_passes central_build long progressive shots on_target goals "
    "pressures press_actions duel_def duel_mid duel_att high_rec ft_rec counter_press losses "
    "own_half_losses line_breaks packing between_lines box z14 half_space n_in n_out"
).split()


class Tally:
    """Per-minute, per-team counters built by walking the raw events once."""

    def __init__(self, events):
        self.m: dict[int, dict[str, defaultdict]] = defaultdict(
            lambda: {"home": defaultdict(float), "away": defaultdict(float)}
        )
        self.pos: dict[tuple[int, str, str], list[float]] = {}
        holder = None
        prev = None
        last_loss: dict[str, float] = {}
        for ev in events:
            me, opp, A = ev.side, other(ev.side), self.m[ev.minute]
            if (
                prev is not None
                and holder is not None
                and prev.period == ev.period
                and 0 < ev.t - prev.t <= 20
            ):
                A[holder]["poss"] += ev.t - prev.t
            prev = ev
            if ev.freeze is not None:
                owner = opp if ev.type in DEFENDING else me
                for side in ("home", "away"):
                    frame = (
                        [tuple(p) for p in ev.freeze.t]
                        if side == me
                        else [(105 - x, 68 - y) for x, y in ev.freeze.o]
                    )
                    role = "in" if side == owner else "out"
                    acc = self.pos.setdefault((ev.minute, side, role), [0.0] * 22)
                    for i, (px, py) in enumerate(frame):
                        acc[2 * i] += px
                        acc[2 * i + 1] += py
                    A[side]["n_" + role] += 1
            S = A[me]
            if ev.type in ("pass", "carry") and ev.end_x is not None and (
                ev.type == "carry" or ev.outcome == "complete"
            ):
                S["xt"] += xt_value(ev.end_x, ev.end_y) - xt_value(ev.x, ev.y)
                S["box"] += in_box(ev.end_x, ev.end_y) and not in_box(ev.x, ev.y)
                S["z14"] += in_z14(ev.end_x, ev.end_y) and not in_z14(ev.x, ev.y)
                S["half_space"] += in_half_space(ev.end_x, ev.end_y) and not in_half_space(
                    ev.x, ev.y
                )
            edge0 = EDGE[0]
            if completed(ev):
                S["packing"] += sum(1 for ox, _ in ev.freeze.o[1:] if ev.x < ox < ev.end_x)
                roles = roles_broken(ev)
                S["line_breaks"] += bool(roles)
                S["line_breaks_back"] += "back" in roles
                S["line_breaks_mid"] += "midfield" in roles
                S["line_breaks_fwd"] += "forward" in roles
                gap = reception_gap(ev)
                S["between_lines"] += gap is not None
                S["between_mid_def"] += gap == "mid_def"
                S["between_fwd_mid"] += gap == "fwd_mid"
                S["edge"] += EDGE[0] - edge0
            if ev.type == "kick_off":
                holder = me
            elif ev.type in ("pass", "carry"):
                holder = me
                if ev.type == "pass":
                    S["passes"] += 1
                    S["complete"] += ev.outcome == "complete"
                    if ev.outcome == "complete" and (
                        ev.end_x - ev.x >= 10 or (ev.x < 70 <= ev.end_x)
                    ):
                        S["progressive"] += 1
                    S["ft_passes"] += ev.x >= 70
                    if ev.x <= 63:
                        S["build_passes"] += 1
                        S["central_build"] += 68 / 3 <= ev.y <= 136 / 3
                    S["long"] += (ev.pass_distance or 0) >= 30
            elif ev.type == "shot":
                S["shots"] += 1
                S["xg"] += ev.xg or 0.0
                S["goals"] += ev.outcome == "goal"
                S["on_target"] += ev.outcome in ("goal", "saved")
                holder = None
            elif ev.type == "pressure":
                S["pressures"] += 1
            elif ev.type in ("tackle", "interception", "foul"):
                S["press_actions"] += ev.x >= 42
                won = ev.type == "interception" or (ev.type == "tackle" and ev.outcome == "won")
                if ev.type in ("tackle", "interception"):
                    win_side, wx = (me, ev.x) if won else (opp, 105 - ev.x)
                    zone = "def" if wx < 35 else "mid" if wx < 70 else "att"
                    A[win_side]["duel_" + zone] += 1
                if won:
                    S["high_rec"] += ev.x >= 52.5
                    S["ft_rec"] += ev.x >= 70
                    if me in last_loss and 0 <= ev.t - last_loss[me] <= 5:
                        S["counter_press"] += 1
                    if holder == opp:
                        A[opp]["losses"] += 1
                        A[opp]["own_half_losses"] += 105 - ev.x < 52.5
                        last_loss[opp] = ev.t
                    holder = me
            elif ev.type == "ball_out":
                if holder == me:
                    S["losses"] += 1
                    S["own_half_losses"] += ev.x < 52.5
                    last_loss[me] = ev.t
                holder = None
            elif ev.type == "half_end":
                holder, prev = None, None

    def window(self, lo: int, hi: int) -> dict:
        """Metrics for minutes lo..hi inclusive, under the production metric names."""
        agg = {s: defaultdict(float) for s in ("home", "away")}
        pos = {(s, r): [0.0] * 22 for s in agg for r in ("in", "out")}
        for m in range(lo, hi + 1):
            if m not in self.m:
                continue
            for s in agg:
                for k, v in self.m[m][s].items():
                    agg[s][k] += v
                for r in ("in", "out"):
                    for i, v in enumerate(self.pos.get((m, s, r), [])):
                        pos[(s, r)][i] += v
        n = hi - lo + 1
        total_poss = (agg["home"]["poss"] + agg["away"]["poss"]) or 1.0
        total_ft = agg["home"]["ft_passes"] + agg["away"]["ft_passes"]
        out: dict = {}
        for s in agg:
            a, o = agg[s], agg[other(s)]
            d = {
                "possession_share": a["poss"] / total_poss,
                "pass_completion": a["complete"] / a["passes"] if a["passes"] else 0.0,
                "field_tilt": a["ft_passes"] / total_ft if total_ft else 0.5,
                "ppda": o["build_passes"] / a["press_actions"] if a["press_actions"] else None,
                "tempo": a["passes"] / (a["poss"] / 60) if a["poss"] / 60 > 0.1 else 0.0,
                "losses_per_min": a["losses"] / n,
                "pressures": a["pressures"],
                "shots": a["shots"],
                "xg": a["xg"],
                "goals": a["goals"],
                "passes": a["passes"],
                "duels_won_def": a["duel_def"],
                "duels_won_mid": a["duel_mid"],
                "duels_won_att": a["duel_att"],
                "high_recoveries": a["high_rec"],
                "final_third_recoveries": a["ft_rec"],
                "counter_press": a["counter_press"],
                "own_half_losses": a["own_half_losses"],
                "progressive_passes": a["progressive"],
                "long_ball_share": a["long"] / a["passes"] if a["passes"] else 0.0,
                "central_buildup_share": (
                    a["central_build"] / a["build_passes"] if a["build_passes"] else 0.0
                ),
                "xt": a["xt"],
                "line_breaks": a["line_breaks"],
                "packing": a["packing"],
                "between_lines": a["between_lines"],
                "edge": a["edge"],
                "line_breaks_back": a["line_breaks_back"],
                "line_breaks_mid": a["line_breaks_mid"],
                "line_breaks_fwd": a["line_breaks_fwd"],
                "between_mid_def": a["between_mid_def"],
                "between_fwd_mid": a["between_fwd_mid"],
                "box_entries": a["box"],
                "zone14_entries": a["z14"],
                "halfspace_entries": a["half_space"],
            }
            for zone, opp_zone in (("def", "att"), ("mid", "mid"), ("att", "def")):
                mine, theirs = a["duel_" + zone], o["duel_" + opp_zone]
                d["duel_share_" + zone] = mine / (mine + theirs) if mine + theirs else None
            for role, suffix in (("out", ""), ("in", "_in")):
                cnt = a["n_" + role]
                if cnt < 8:
                    d["formation_" + role] = None
                    continue
                avg = [(pos[(s, role)][2 * i] / cnt, pos[(s, role)][2 * i + 1] / cnt) for i in range(11)]
                xs = [p[0] for p in avg[1:]]
                ys = [p[1] for p in avg[1:]]
                groups = lines_of(xs)

                def mean(g, xs=xs):
                    return sum(xs[i] for i in g) / len(g)

                d["formation_" + role] = float("".join(str(len(g)) for g in groups))
                d["line_height" + suffix] = mean(groups[0])
                if role == "out":
                    d["gap_def_mid"] = mean(groups[1]) - mean(groups[0])
                    d["gap_mid_att"] = mean(groups[-1]) - mean(groups[-2])
                    d["team_length"] = max(xs) - min(xs)
                    d["team_width"] = max(ys) - min(ys)
            out[s] = d
        out["turnovers_per_min"] = (agg["home"]["losses"] + agg["away"]["losses"]) / n
        return out


@cache
def tally(seed: int) -> Tally:
    return Tally(played(seed)[0].events)


# tolerance = half a unit of the last decimal production rounds to
TOL = {
    "possession_share": 6e-4, "pass_completion": 6e-4, "field_tilt": 6e-4,
    "duel_share_def": 6e-4, "duel_share_mid": 6e-4, "duel_share_att": 6e-4,
    "long_ball_share": 6e-4, "central_buildup_share": 6e-4,
    "ppda": 0.051, "tempo": 0.051, "losses_per_min": 0.006, "xg": 0.0051, "xt": 6e-4,
    "line_height": 0.051, "line_height_in": 0.051, "gap_def_mid": 0.051, "gap_mid_att": 0.051,
    "team_length": 0.051, "team_width": 0.051,
}


def close(name: str, prod, ind) -> bool:
    if prod is None or ind is None:
        return prod is None and ind is None
    return abs(prod - ind) <= TOL.get(name, 1e-9) + 1e-9


WINDOW_METRICS = [
    "possession_share", "pass_completion", "field_tilt", "ppda", "tempo", "losses_per_min",
    "pressures", "shots", "xg", "goals", "passes", "duels_won_def", "duels_won_mid",
    "duels_won_att", "duel_share_def", "duel_share_mid", "duel_share_att", "high_recoveries",
    "final_third_recoveries", "counter_press", "own_half_losses", "progressive_passes",
    "long_ball_share", "central_buildup_share", "xt", "line_breaks", "packing", "between_lines",
    "line_breaks_back", "line_breaks_mid", "line_breaks_fwd", "between_mid_def", "between_fwd_mid",
    "box_entries", "zone14_entries", "halfspace_entries", "line_height", "line_height_in",
    "gap_def_mid", "gap_mid_att", "team_length", "team_width",
]


DAMAGE_METRICS = {
    "line_breaks", "line_breaks_back", "line_breaks_mid", "line_breaks_fwd", "between_lines",
    "between_mid_def", "between_fwd_mid",
}


def compare_window(prod_team: dict, ind_team: dict, where: str, bad: list[str]) -> int:
    n = 0
    for name in WINDOW_METRICS:
        if name not in ind_team:  # shape metrics are absent below 8 frames
            assert prod_team[name] is None, (where, name)
            continue
        n += 1
        if name in DAMAGE_METRICS and abs(prod_team[name] - ind_team[name]) <= ind_team["edge"]:
            continue
        if not close(name, prod_team[name], ind_team[name]):
            bad.append(f"{where} {name}: shown {prod_team[name]} vs independent {ind_team[name]}")
    for role in ("out", "in"):
        n += 1
        got = prod_team["formation_" + role]
        if not close("formation", got, ind_team.get("formation_" + role)):
            bad.append(f"{where} formation_{role}: shown {got} vs {ind_team.get('formation_' + role)}")
    return n


# ====================================================================== 1. clock and halves
@pytest.mark.parametrize("seed", SEEDS)
def test_clock_and_halves(seed):
    ev = sim(seed).events
    assert [e.seq for e in ev] == list(range(1, len(ev) + 1))
    assert all(a.t <= b.t for a, b in zip(ev, ev[1:], strict=False)), "match clock went backwards"
    assert all(e.minute == int(e.t // 60) for e in ev)
    for e in ev:
        if e.period == 1:
            assert e.t < 2700 and e.minute <= 44, f"first-half event at {e.t}"
        else:
            assert e.t >= 2700 and e.minute >= 45
        # the studio's clock label ("second half" from 45') must agree with the period
        assert (int(e.t // 60) >= 45) == (e.period == 2)
    ends = [e for e in ev if e.type == "half_end"]
    assert [e.period for e in ends] == [1, 2]
    second_start = next(e for e in ev if e.period == 2)
    assert second_start.type == "kick_off" and second_start.t == 2700.0
    full_time = ends[1]
    assert ev[-1] is full_time
    assert 5460 <= full_time.t <= 5400 + 300 + 120, "1-5 minutes added, plus the last move"


# ====================================================================== 2. scores
@pytest.mark.parametrize("seed", SEEDS)
def test_score_everywhere_equals_goal_events(seed):
    match, orch = played(seed)
    goals = {"home": 0, "away": 0}
    for e in match.events:
        if e.type == "shot" and e.outcome == "goal":
            goals[e.side] += 1
        assert (e.score_home, e.score_away) == (goals["home"], goals["away"]), e.id
    final = (goals["home"], goals["away"])
    assert (orch.state.score["home"], orch.state.score["away"]) == final
    assert (orch.recap.score_home, orch.recap.score_away) == final
    # the recap claims carry the same score and the headline prints it
    claims = {c.key: c.value for c in orch.recap.claims}
    assert (claims["sh"], claims["sa"]) == final
    assert re.search(rf"\b{final[0]}\D{final[1]}\b", orch.recap.headline)

    # the studio scorebug and the broadcast bug show the last `event` record it received:
    # the replay must therefore deliver events in match order
    feed = [r for r in build_feed(orch) if r["type"] == "event"]
    seqs = [int(r["data"]["id"].rsplit("-", 1)[1]) for r in feed]
    assert seqs == sorted(seqs), "events replayed out of order: the scorebug would regress"
    assert (feed[-1]["data"]["score_home"], feed[-1]["data"]["score_away"]) == final

    # broadcast lower third: a goal cue prints the score after that goal
    by_id = {e.id: e for e in match.events}
    for cue in orch.cues:
        if cue.kind != "goal":
            continue
        ev = by_id[cue.evidence_event_ids[0]]
        m = re.search(r"(\d+)\D(\d+)", cue.headline)
        assert m and (int(m[1]), int(m[2])) == (ev.score_home, ev.score_away), cue.headline


@pytest.mark.parametrize("seed", [0, 7, 1003])
def test_personal_recap_score(seed):
    match, orch = played(seed)
    final = (orch.state.score["home"], orch.state.score["away"])
    for mode in ("analyst", "fan", "player_focus", "coach"):
        for lang in ("en", "es", "ca"):
            r = orch.recap_for(Viewer(mode=mode, lang=lang, club="home"))
            assert (r.score_home, r.score_away) == final
            claims = {c.key: c.value for c in r.claims}
            assert (claims["sh"], claims["sa"]) == final
            assert re.search(rf"\b{final[0]}\D{final[1]}\b", r.headline), (mode, lang, r.headline)


# ====================================================================== 3. windows and scopes
@pytest.mark.parametrize("seed", SEEDS)
def test_every_window_and_match_scope_matches_independent(seed):
    """Per minute: the 5-minute window (head-to-head 'window') and the whole match so far
    ('match') shown by the UI against the independent recomputation."""
    _, orch = played(seed)
    t = tally(seed)
    pulses = [r["data"] for r in orch.bus if r["type"] == "pulse"]
    assert pulses
    bad: list[str] = []
    checked = 0
    for p in pulses:
        m = p["minute"]
        for scope, lo in (("window", max(0, m - 4)), ("match", 0)):
            ind = t.window(lo, m)
            src = p if scope == "window" else p["match"]
            for side in ("home", "away"):
                checked += compare_window(src[side], ind[side], f"seed {m}' {scope} {side}", bad)
        ind5 = t.window(max(0, m - 4), m)
        if abs(p["turnovers_per_min"] - ind5["turnovers_per_min"]) > 0.006:
            bad.append(f"{m}' turnovers_per_min {p['turnovers_per_min']} vs {ind5['turnovers_per_min']}")
        # momentum bars: xT created in this single minute
        one = t.window(m, m)
        for side in ("home", "away"):
            if abs(p["xt_minute"][side] - one[side]["xt"]) > 6e-4:
                bad.append(f"{m}' xt_minute {side}")
    assert not bad, f"{len(bad)} of {checked} numbers differ, e.g. " + "; ".join(bad[:8])
    # head-to-head 'match' scope at full time equals the totals of the whole event log
    last = pulses[-1]["match"]
    ev = played(seed)[0].events
    for side in ("home", "away"):
        mine = [e for e in ev if e.side == side]
        assert last[side]["shots"] == sum(e.type == "shot" for e in mine)
        assert last[side]["passes"] == sum(e.type == "pass" for e in mine)
        assert last[side]["goals"] == sum(e.type == "shot" and e.outcome == "goal" for e in mine)


@pytest.mark.parametrize("seed", SEEDS)
def test_shots_on_target_xg_and_accuracy_totals(seed):
    """Full-match totals straight from the log: shots, on target, xG, pass accuracy."""
    match, orch = played(seed)
    match_scope = [r["data"] for r in orch.bus if r["type"] == "pulse"][-1]["match"]
    for side in ("home", "away"):
        mine = [e for e in match.events if e.side == side]
        shots = [e for e in mine if e.type == "shot"]
        passes = [e for e in mine if e.type == "pass"]
        assert match_scope[side]["shots"] == len(shots)
        assert sum(e.outcome in ("goal", "saved") for e in shots) <= len(shots)
        assert match_scope[side]["xg"] == pytest.approx(sum(e.xg for e in shots), abs=0.0051)
        assert orch.state.team_xg[side] == pytest.approx(sum(e.xg for e in shots))
        if passes:
            acc = sum(e.outcome == "complete" for e in passes) / len(passes)
            assert match_scope[side]["pass_completion"] == pytest.approx(acc, abs=6e-4)
    # possession shares add up to one
    total = match_scope["home"]["possession_share"] + match_scope["away"]["possession_share"]
    assert total == pytest.approx(1.0, abs=0.0021)
    tilt = match_scope["home"]["field_tilt"] + match_scope["away"]["field_tilt"]
    assert tilt == pytest.approx(1.0, abs=0.0021)


# ====================================================================== 4. verifier claims
def indep_buildup(events, shot):
    idx = next(k for k, e in enumerate(events) if e.id == shot.id)
    first = idx
    while first > 0 and events[first - 1].possession_id == shot.possession_id:
        first -= 1
    long_balls = sum(
        e.type == "pass" and e.side == shot.side and e.outcome == "complete"
        and (e.pass_distance or 0) >= 30
        for e in events[first : idx + 1]
    )
    rec = events[first - 1] if first > 0 else None
    if not (
        rec and rec.side == shot.side
        and (rec.type == "interception" or (rec.type == "tackle" and rec.outcome == "won"))
    ):
        return None, 0, long_balls
    counter = 0
    for e in reversed(events[: first - 1]):
        if rec.t - e.t > 5:
            break
        if (
            (e.side != shot.side and (e.type == "interception" or (e.type == "tackle" and e.outcome == "won")))
            or (e.type == "ball_out" and e.side == shot.side)
        ):
            counter = 1
            break
    return round(shot.t - rec.t, 1), counter, long_balls


def indep_claim(seed: int, c):
    """The independent value of a claim, or the string 'skip' for a metric not rebuilt here."""
    match = played(seed)[0]
    events = match.events
    by_id = {e.id: e for e in events}
    t = tally(seed)
    if c.metric in WINDOW_METRICS or c.metric in ("turnovers_per_min", "formation_in", "formation_out"):
        lo, hi = c.window
        w = t.window(lo, hi)
        if c.metric == "turnovers_per_min":
            return w["turnovers_per_min"]
        return w[c.side].get(c.metric)
    if c.metric == "window_minutes":
        return float(c.window[1] - c.window[0] + 1)
    if c.metric == "team_xg":
        upto = by_id[c.event_id].seq if c.event_id else len(events)
        return sum(e.xg for e in events if e.type == "shot" and e.side == c.side and e.seq <= upto)
    if c.metric in ("xt_share_left", "xt_share_centre", "xt_share_right"):
        lo, hi = c.window
        lanes = [0.0, 0.0, 0.0]
        for e in events:
            if (
                e.side == c.side and lo <= e.minute <= hi and e.end_x is not None
                and (e.type == "carry" or completed(e))
            ):
                added = xt_value(e.end_x, e.end_y) - xt_value(e.x, e.y)
                if added > 0:
                    lanes[0 if e.end_y < 68 / 3 else 1 if e.end_y < 136 / 3 else 2] += added
        total = sum(lanes)
        idx = ("xt_share_left", "xt_share_centre", "xt_share_right").index(c.metric)
        return round(lanes[idx] / total, 3) if total > 0 else None
    ev = by_id.get(c.event_id or "")
    if ev is None:
        return None
    if c.metric == "shot_xg":
        return ev.xg
    if c.metric == "score_home":
        return float(sum(e.type == "shot" and e.outcome == "goal" and e.side == "home"
                         for e in events if e.seq <= ev.seq))
    if c.metric == "score_away":
        return float(sum(e.type == "shot" and e.outcome == "goal" and e.side == "away"
                         for e in events if e.seq <= ev.seq))
    if c.metric in ("carry_speed_kmh", "shot_speed_kmh"):
        return ev.ball_speed_kmh
    if c.metric == "pass_difficulty":
        return ev.pass_difficulty
    if c.metric == "pass_xt_added":
        return xt_value(ev.end_x, ev.end_y) - xt_value(ev.x, ev.y) if completed(ev) else None
    if c.metric == "pass_packing":
        return float(sum(1 for ox, _ in ev.freeze.o[1:] if ev.x < ox < ev.end_x)) if completed(ev) else None
    if c.metric in ("buildup_seconds", "counter_press_in_move", "long_balls_in_move"):
        secs, counter, long_balls = indep_buildup(events, ev)
        return {"buildup_seconds": secs, "counter_press_in_move": float(counter),
                "long_balls_in_move": float(long_balls)}[c.metric]
    if c.metric == "player_completed_passes":
        return float(sum(completed(e) and e.player_id == c.player_id
                         for e in events if e.seq <= ev.seq))
    return "skip"


@pytest.mark.parametrize("seed", SEEDS)
def test_every_verifier_claim_equals_independent_value(seed):
    _, orch = played(seed)
    claims = [c for ins in orch.insights for c in ins.claims] + list(orch.recap.claims)
    assert claims
    bad = []
    for c in claims:
        ind = indep_claim(seed, c)
        if isinstance(ind, str):
            bad.append(f"no independent source for {c.metric}")
            continue
        if ind is None or abs(ind - c.value) > c.tolerance + 1e-6 + (
            tally(seed).window(*c.window)[c.side]["edge"]
            if c.metric in DAMAGE_METRICS and c.window else 0
        ):
            bad.append(f"{c.metric} {c.key} stated {c.value}, independent {ind}")
    assert not bad, "; ".join(bad[:8])


# ====================================================================== 5. players tab
def ui_tally(feed):
    """web/app.js tallyPlayer(), line for line, over the replayed `event` records."""
    pl: dict[str, defaultdict] = defaultdict(lambda: defaultdict(float))
    for r in feed:
        d = r["data"]
        pid = d.get("player_id")
        if r["type"] != "event" or not pid:
            continue
        p = pl[pid]
        if d["type"] == "pass":
            p["passes"] += 1
            p["done"] += d.get("outcome") == "complete"
        p["xt"] += d.get("xt", 0) or 0
        p["lb"] += bool(d.get("lb"))
        p["pk"] += d.get("pk", 0) or 0
        if d["type"] == "shot":
            p["shots"] += 1
            p["xg"] += d.get("xg") or 0
            p["goals"] += d.get("outcome") == "goal"
        if d["type"] == "interception" or (d["type"] == "tackle" and d.get("outcome") == "won"):
            p["wins"] += 1
        if d["type"] == "carry" and d.get("ball_speed_kmh"):
            p["speed"] = max(p["speed"], d["ball_speed_kmh"])
    return pl


@pytest.mark.parametrize("seed", SEEDS)
def test_players_tab_sums_equal_team_totals(seed):
    match, orch = played(seed)
    pl = ui_tally(build_feed(orch))
    meta = match.meta
    roster = {p.id: s for s, team in (("home", meta.home), ("away", meta.away)) for p in team.players}
    # no substitutions in the log: every player on the sheet plays the full match
    assert {e.player_id for e in match.events if e.player_id} <= set(roster)
    assert all(roster[e.player_id] == e.side for e in match.events if e.player_id)
    t = tally(seed)
    last = max(e.minute for e in match.events)
    full = t.window(0, last)
    for side in ("home", "away"):
        mine = [p for pid, p in pl.items() if roster[pid] == side]
        total = lambda k, mine=mine: sum(p[k] for p in mine)  # noqa: E731
        tm = full[side]
        assert total("passes") == tm["passes"]
        assert total("shots") == tm["shots"]
        assert total("goals") == tm["goals"]
        assert total("xg") == pytest.approx(tm["xg"], abs=1e-6)
        assert total("lb") == tm["line_breaks"]
        assert total("pk") == tm["packing"]
        # a player's "ball wins" are the team's tackles won plus interceptions
        wins = sum(
            e.type == "interception" or (e.type == "tackle" and e.outcome == "won")
            for e in match.events if e.side == side
        )
        assert total("wins") == wins
        # the API rounds each pass's xT to 3 dp before the player table adds them up
        assert total("xt") == pytest.approx(tm["xt"], abs=0.0006 * 600)
        assert total("done") == sum(
            completed(e) for e in match.events if e.side == side
        )
    # per player, against the raw log
    for pid, p in pl.items():
        assert p["passes"] == sum(e.type == "pass" and e.player_id == pid for e in match.events)
        assert p["done"] == sum(completed(e) and e.player_id == pid for e in match.events)
    # the table sorts a column in descending order (JS sort is stable: ties keep roster order)
    rows = [(pid, pl[pid]["done"]) for pid in roster if pid in pl]
    ranked = sorted(rows, key=lambda r: -r[1])
    assert [r[1] for r in ranked] == sorted((r[1] for r in rows), reverse=True)


# ====================================================================== 6. realism
# Premier League reference: football-data.co.uk match results (E0.csv, all 380 matches of each
# of 2023-24, 2024-25 and 2025-26; https://www.football-data.co.uk/englandm.php). Computed
# per season, shown here as (min, max) across the three seasons.
REF = {
    "goals": (2.75, 3.28),
    "p_0_0": (0.029, 0.071),
    "p_6plus": (0.042, 0.095),
    "home": (0.408, 0.461),
    "draw": (0.216, 0.274),
    "away": (0.300, 0.347),
    "shots_per_team": (12.50, 13.79),
    "sot_per_team": (4.19, 4.93),
}


@lru_cache(maxsize=1)
def distribution():
    rows = []
    for seed in range(100):
        ev = sim(seed).events
        g = {s: sum(e.type == "shot" and e.outcome == "goal" and e.side == s for e in ev)
             for s in ("home", "away")}
        shots = {s: [e for e in ev if e.type == "shot" and e.side == s] for s in g}
        rows.append((seed, g["home"], g["away"], len(shots["home"]), len(shots["away"]),
                     sum(e.outcome in ("goal", "saved") for s in shots for e in shots[s])))
    n = len(rows)
    total = [r[1] + r[2] for r in rows]
    return {
        "goals": statistics.mean(total),
        "p_0_0": sum(x == 0 for x in total) / n,
        "p_6plus": sum(x >= 6 for x in total) / n,
        "home": sum(r[1] > r[2] for r in rows) / n,
        "draw": sum(r[1] == r[2] for r in rows) / n,
        "away": sum(r[1] < r[2] for r in rows) / n,
        "shots_per_team": statistics.mean(r[3] + r[4] for r in rows) / 2,
        "sot_per_team": statistics.mean(r[5] for r in rows) / 2,
        "rows": rows,
    }


# n = 100 matches: allow roughly two standard errors around the reference range
BAND = {
    "goals": 0.25, "p_0_0": 0.04, "p_6plus": 0.05, "home": 0.09, "draw": 0.09, "away": 0.09,
    "shots_per_team": 1.0, "sot_per_team": 0.6,
}


@pytest.mark.parametrize("name", list(REF))
def test_match_distribution_is_premier_league_like(name):
    lo, hi = REF[name]
    got = distribution()[name]
    assert lo - BAND[name] <= got <= hi + BAND[name], f"{name}: {got:.3f} vs reference {lo}-{hi}"


def test_no_implausible_scorelines():
    rows = distribution()["rows"]
    # a 1-5 or 0-4 result does happen (margin 4+ is ~2-9 % of PL matches); 0-7 or 8+ goals do not
    margin4 = sum(abs(r[1] - r[2]) >= 4 for r in rows) / len(rows)
    assert margin4 <= 0.10
    assert max(r[1] + r[2] for r in rows) <= 8
    assert max(abs(r[1] - r[2]) for r in rows) <= 6
    assert max(max(r[1], r[2]) for r in rows) <= 7

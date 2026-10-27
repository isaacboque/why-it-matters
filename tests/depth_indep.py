# ruff: noqa: E501
"""Independent recomputation of the depth metrics (pressing, chances, hub, physical, ratings).

Written from the definitions in docs/METHODS.md and the docstrings of pulse/metrics.py,
pulse/chances.py, pulse/physical.py and pulse/ratings.py. It imports nothing from
`whyitmatters.pulse`; the damage helpers it needs (line and reception rules) come from the
already independent ones in tests/test_stats_audit.py.
"""

from __future__ import annotations

import math
from collections import defaultdict

CHECK_S, MAX_GAP_S, HIGH_KMH, SPRINT_KMH = 4.0, 15.0, 20.0, 25.0


def _audit():
    import test_stats_audit as audit  # lazy: that module imports this one for its claim checks

    return audit


def wide(y: float) -> bool:
    return not (68 / 3 <= y < 136 / 3)


def shot_kind(prev, shot, audit) -> str:
    ok = (
        prev is not None and prev.type == "pass" and prev.outcome == "complete"
        and prev.side == shot.side and prev.end_x is not None
        and prev.receiver_id is not None and prev.receiver_id == shot.player_id
    )
    if ok:
        if prev.x >= 94 and wide(prev.y) and audit.in_box(prev.end_x, prev.end_y) and prev.x - prev.end_x >= 3:
            return "cutback"
        if prev.x >= 70 and wide(prev.y) and audit.in_box(prev.end_x, prev.end_y):
            return "cross"
        if "back" in audit.roles_broken(prev):
            return "through"
    return "long" if audit.goal_dist(shot.x, shot.y) >= 25 else "other"


class DepthTally:
    def __init__(self, events, roster: dict[str, list[str]] | None = None):
        A = _audit()
        self.m: dict[int, dict[str, defaultdict]] = defaultdict(
            lambda: {"home": defaultdict(float), "away": defaultdict(float)}
        )
        self.inv: dict[int, dict[str, defaultdict]] = defaultdict(
            lambda: {"home": defaultdict(int), "away": defaultdict(int)}
        )
        self.player: dict[str, defaultdict] = defaultdict(lambda: defaultdict(float))
        self.roster = roster or {}
        pressures: dict[str, list[float]] = {"home": [], "away": []}
        prev = None
        cp: dict[str, tuple] = {}
        acted: dict[str, set] = {"home": set(), "away": set()}
        for ev in events:
            S = self.m[ev.minute][ev.side]
            edge0 = A.EDGE[0]
            # ---- physical: checkpoints every >= 4 s, no credit across kick-offs, half-time or gaps
            if ev.type in ("half_end", "kick_off") or ev.freeze is None:
                cp.clear()
                acted = {"home": set(), "away": set()}
            if ev.freeze is not None:
                if ev.type != "kick_off":
                    for i, (px, py) in enumerate(ev.freeze.t):
                        if abs(px - ev.x) < 0.06 and abs(py - ev.y) < 0.06:
                            acted[ev.side].add(i)
                for side in ("home", "away"):
                    frame = (
                        [tuple(p) for p in ev.freeze.t] if side == ev.side
                        else [(105 - x, 68 - y) for x, y in ev.freeze.o]
                    )
                    old = cp.get(side)
                    if old is not None and old[0] == ev.period:
                        dt = ev.t - old[1]
                        if dt < CHECK_S:
                            continue
                        if dt <= MAX_GAP_S:
                            for i in range(1, 11):
                                if i in acted[side]:
                                    continue
                                d = math.dist(old[2][i], frame[i])
                                kmh = d / dt * 3.6
                                T = self.m[ev.minute][side]
                                T["dist"] += d
                                T["sprints"] += kmh >= SPRINT_KMH
                                T["hsr"] += kmh >= HIGH_KMH
                                T["top"] = max(T["top"], kmh)
                                if self.roster:
                                    P = self.player[self.roster[side][i]]
                                    P["distance_m"] += d
                                    P["sprints"] += kmh >= SPRINT_KMH
                                    P["top_speed_kmh"] = max(P["top_speed_kmh"], kmh)
                    cp[side] = (ev.period, ev.t, frame)
                    acted[side] = set()
            # ---- pressing
            if ev.type == "pressure":
                pressures[ev.side].append(ev.t)
            won = ev.type == "interception" or (ev.type == "tackle" and ev.outcome == "won")
            if won:
                S["regains"] += 1
                S["regains_wide"] += wide(ev.y)
                if any(0 <= ev.t - t <= 5 for t in pressures[ev.side]):
                    S["press_wins"] += 1
                    pressures[ev.side] = []
            # ---- escapes and involvement
            if A.completed(ev):
                if ev.x <= 63:
                    gap = A.reception_gap(ev)
                    if "forward" in A.roles_broken(ev) or gap == "fwd_mid":
                        S["esc_short"] += 1
                    elif (ev.pass_distance or 0) >= 30:
                        S["esc_long"] += 1
                S["complete"] += 1
                self.inv[ev.minute][ev.side][ev.player_id] += 1
                self.inv[ev.minute][ev.side][ev.receiver_id] += 1
            if ev.type == "pass":
                S["pass"] += 1
                if ev.x <= 63:
                    S["build"] += 1
            # ---- chances
            if ev.type == "shot":
                S["shots"] += 1
                S["xg"] += ev.xg or 0.0
                S["goals"] += ev.outcome == "goal"
                S["big"] += (ev.xg or 0.0) >= 0.3
                kind = shot_kind(prev, ev, A)
                if kind != "other":
                    S["shots_" + kind] += 1
            S["edge"] += A.EDGE[0] - edge0
            prev = ev
            # ---- players
            if self.roster and ev.player_id:
                P = self.player[ev.player_id]
                if ev.type == "pass":
                    P["passes"] += 1
                    if A.completed(ev):
                        P["completed"] += 1
                        P["involvement"] += 1
                        self.player[ev.receiver_id]["involvement"] += 1
                        P["xt"] += A.xt_value(ev.end_x, ev.end_y) - A.xt_value(ev.x, ev.y)
                        if ev.end_x - ev.x >= 10 or (ev.x < 70 <= ev.end_x):
                            P["progressive"] += 1
                        P["line_breaks"] += bool(A.roles_broken(ev))
                    else:
                        P["incomplete"] += 1
                elif ev.type == "carry" and ev.end_x is not None:
                    P["xt"] += A.xt_value(ev.end_x, ev.end_y) - A.xt_value(ev.x, ev.y)
                    if ev.end_x - ev.x >= 10:
                        P["progressive"] += 1
                elif ev.type == "shot":
                    P["shots"] += 1
                    P["xg"] += ev.xg or 0.0
                    P["goals"] += ev.outcome == "goal"
                if won:
                    P["wins"] += 1
                if ev.type == "tackle" and ev.outcome == "lost":
                    P["lost_duels"] += 1
        # key passes: a completed pass straight before a shot by its receiver
        if self.roster:
            for a, b in zip(events, events[1:], strict=False):
                if (
                    b.type == "shot" and A.completed(a) and a.side == b.side
                    and a.receiver_id == b.player_id
                ):
                    self.player[a.player_id]["key_passes"] += 1
                    self.player[a.player_id]["xa"] += b.xg or 0.0

    def window(self, lo: int, hi: int) -> dict:
        n = hi - lo + 1
        out = {}
        for side in ("home", "away"):
            a: defaultdict = defaultdict(float)
            inv: defaultdict = defaultdict(int)
            for m in range(lo, hi + 1):
                if m not in self.m:
                    continue
                for k, v in self.m[m][side].items():
                    a[k] = max(a[k], v) if k == "top" else a[k] + v
                for pid, c in self.inv[m][side].items():
                    inv[pid] += c
            done = a["complete"]
            hub = min(inv.items(), key=lambda kv: (-kv[1], kv[0]), default=None)
            esc = a["esc_short"] + a["esc_long"]
            out[side] = {
                "edge": a["edge"],
                "press_wins": a["press_wins"],
                "regains": a["regains"],
                "regains_wide_share": a["regains_wide"] / a["regains"] if a["regains"] else 0.0,
                "press_escapes_short": a["esc_short"],
                "press_escapes_long": a["esc_long"],
                "press_escapes": esc,
                "press_escape_rate": esc / a["build"] if a["build"] else 0.0,
                "big_chances": a["big"],
                "xg_per_shot": a["xg"] / a["shots"] if a["shots"] else 0.0,
                "finishing": a["goals"] - a["xg"],
                "shots_cutback": a["shots_cutback"],
                "shots_cross": a["shots_cross"],
                "shots_through": a["shots_through"],
                "shots_long": a["shots_long"],
                "hub_player": hub[0] if hub and done else None,
                "hub_share": hub[1] / done if hub and done else 0.0,
                "involvement": {k: v / done for k, v in inv.items()} if done else {},
                "distance_per_min": a["dist"] / 10 / n,
                "sprints": a["sprints"],
                "high_speed_runs": a["hsr"],
                "top_speed_kmh": a["top"],
            }
        return out

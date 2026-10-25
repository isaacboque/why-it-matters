"""Expected Threat (xT): how likely a possession is to end in a goal from each zone.

Position-based xT (Karun Singh, 2018). The pitch is a 16 x 12 grid in the acting team's
coordinates. For each zone z, from all actions that start there:

    xT(z) = P(shoot | z) * P(goal | shot, z) + P(move | z) * sum_z' T(z -> z') * xT(z')

where a move is a pass or a carry, T(z -> z') is the share of moves from z that SUCCEED and
end in z' (failed moves lead nowhere and add nothing), and P(goal | shot, z) is the mean xG of
shots from z. The equation is solved by iterating from xT = 0 until it settles.

An action's value is xT added = xT(end zone) - xT(start zone). The fitted grid ships as
`xt_grid.json`; refit with `python -m whyitmatters.pulse.xt --fit --seeds 200`.
Fitted on simulated matches, so the values describe the simulator's football; with real
event data only the input changes.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH, EventType, Outcome

NX, NY = 16, 12
ZONES18 = 18  # 6 lengths x 3 widths, for damage maps
GRID_FILE = Path(__file__).with_name("xt_grid.json")


def cell(x: float, y: float) -> tuple[int, int]:
    i = min(NX - 1, max(0, int(x / (PITCH_LENGTH / NX))))
    j = min(NY - 1, max(0, int(y / (PITCH_WIDTH / NY))))
    return i, j


def zone18(x: float, y: float) -> int:
    """Index of the 6 x 3 zone (lengths from own goal, then widths)."""
    i = min(5, max(0, int(x / (PITCH_LENGTH / 6))))
    j = min(2, max(0, int(y / (PITCH_WIDTH / 3))))
    return i * 3 + j


@lru_cache(maxsize=1)
def grid() -> list[list[float]]:
    if not GRID_FILE.exists():
        return [[0.0] * NY for _ in range(NX)]
    return json.loads(GRID_FILE.read_text())["xt"]


def value(x: float, y: float) -> float:
    i, j = cell(x, y)
    return grid()[i][j]


def added(x: float, y: float, end_x: float, end_y: float) -> float:
    """xT added by moving the ball from (x, y) to (end_x, end_y)."""
    return value(end_x, end_y) - value(x, y)


def fit(matches, iterations: int = 40) -> list[list[float]]:
    shots = [[0] * NY for _ in range(NX)]
    shot_xg = [[0.0] * NY for _ in range(NX)]
    moves = [[0] * NY for _ in range(NX)]
    trans: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
    for m in matches:
        for ev in m.events:
            if ev.type == EventType.SHOT:
                i, j = cell(ev.x, ev.y)
                shots[i][j] += 1
                shot_xg[i][j] += ev.xg or 0.0
            elif ev.type in (EventType.PASS, EventType.CARRY) and ev.end_x is not None:
                i, j = cell(ev.x, ev.y)
                moves[i][j] += 1
                if ev.type == EventType.CARRY or ev.outcome == Outcome.COMPLETE:
                    k = cell(ev.end_x, ev.end_y)
                    row = trans.setdefault((i, j), {})
                    row[k] = row.get(k, 0) + 1
    xt = [[0.0] * NY for _ in range(NX)]
    for _ in range(iterations):
        new = [[0.0] * NY for _ in range(NX)]
        for i in range(NX):
            for j in range(NY):
                total = shots[i][j] + moves[i][j]
                if not total:
                    continue
                p_shot = shots[i][j] / total
                p_goal = shot_xg[i][j] / shots[i][j] if shots[i][j] else 0.0
                move_val = 0.0
                if moves[i][j]:
                    for (a, b), n in trans.get((i, j), {}).items():
                        move_val += n / moves[i][j] * xt[a][b]
                new[i][j] = p_shot * p_goal + (moves[i][j] / total) * move_val
        xt = new
    return [[round(v, 5) for v in row] for row in xt]


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit the xT grid on simulated matches")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--seeds", type=int, default=200)
    args = ap.parse_args()
    if not args.fit:
        g = grid()
        for j in reversed(range(NY)):
            print(" ".join(f"{g[i][j]:.3f}" for i in range(NX)))
        return
    from whyitmatters.simulator import simulate

    g = fit(simulate(s) for s in range(args.seeds))
    GRID_FILE.write_text(json.dumps({"nx": NX, "ny": NY, "seeds": args.seeds, "xt": g}))
    grid.cache_clear()
    print(f"wrote {GRID_FILE}; max xT {max(max(r) for r in g):.3f}")


if __name__ == "__main__":
    main()

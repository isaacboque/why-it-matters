"""A small, transparent expected-goals model (distance + opening angle)."""

from __future__ import annotations

import math

from whyitmatters.schema import PITCH_LENGTH, PITCH_WIDTH

GOAL_HALF_WIDTH = 3.66
ANGLE_WEIGHT = 1.3
XG_SCALE = 0.90  # lower per-shot value: league-like xG per shot and team xG (docs/STATS-AUDIT.md)


def opening_angle(x: float, y: float) -> float:
    """Angle in radians subtended by the goalposts from (x, y)."""
    dx = max(PITCH_LENGTH - x, 0.5)
    left = math.atan2(PITCH_WIDTH / 2 + GOAL_HALF_WIDTH - y, dx)
    right = math.atan2(PITCH_WIDTH / 2 - GOAL_HALF_WIDTH - y, dx)
    return abs(left - right)


def distance_to_goal(x: float, y: float) -> float:
    return math.hypot(PITCH_LENGTH - x, PITCH_WIDTH / 2 - y)


def expected_goals(x: float, y: float, under_pressure: bool = False) -> float:
    z = -1.25 + ANGLE_WEIGHT * opening_angle(x, y) - 0.09 * distance_to_goal(x, y)
    xg = XG_SCALE / (1.0 + math.exp(-z))
    if under_pressure:
        xg *= 0.7
    return round(min(max(xg, 0.01), 0.95), 3)

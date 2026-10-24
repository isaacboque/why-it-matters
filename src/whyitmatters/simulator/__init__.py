"""Synthetic match simulator with ground truth."""

from whyitmatters.simulator.engine import Simulator, simulate
from whyitmatters.simulator.io import read_match, write_match

__all__ = ["Simulator", "simulate", "read_match", "write_match"]

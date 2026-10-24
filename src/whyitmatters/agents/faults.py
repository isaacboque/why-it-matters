"""Fault injection: simulates a model that sometimes mis-states a number on its first draft.

Used by tests and by the demo's "unreliable model" switch to prove the Verifier catches
bad numbers. It is never active unless a `FaultInjector` is passed in explicitly.
"""

from __future__ import annotations

import random

from whyitmatters.agents.models import Claim

PERTURB = {"share": 0.12, "count": 3, "xg": 0.15, "kmh": 4.0, "rate": 1.5, "minutes": 2}


class FaultInjector:
    def __init__(self, rate: float, seed: int = 0):
        self.rate = rate
        self.rng = random.Random(seed)

    def corrupt(self, claims: list[Claim]) -> list[Claim]:
        """With probability `rate`, return the claims with one value made wrong."""
        if not claims or self.rng.random() >= self.rate:
            return claims
        victim = self.rng.randrange(len(claims))
        c = claims[victim]
        bumped = c.value + PERTURB[c.unit]
        if c.unit == "share" and bumped > 0.99:
            bumped = c.value - PERTURB["share"]
        out = list(claims)
        out[victim] = c.model_copy(update={"value": round(bumped, 3)})
        return out

"""Match Pulse: a streaming state model of who controls the game, and when it turns to chaos.

Each closed minute produces a PulseSnapshot over a rolling window. Two indices drive it:
- dominance in [-1, 1]: positive = home in control, negative = away in control
  (possession share and pass-completion gap; field tilt is reported but too noisy to drive it)
- chaos in [0, 1]: turnover rate and broken passing, regardless of who has the ball

A state change is only confirmed after it holds for `confirm` consecutive minutes, so the
studio never sees a flicker. Every transition carries the metrics before and after plus the
event ids behind them, which the Verifier later checks claims against.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from whyitmatters.pulse.metrics import MinuteCounter, WindowMetrics
from whyitmatters.schema import Event, EventType, MatchMeta, PhaseKind

State = PhaseKind

DOMINANCE_THRESHOLD = 0.25
CHAOS_THRESHOLD = 0.55
STICKINESS = 1.0  # <1 enables hysteresis; tuning on seeds 0-39 found no gain
DOMINANCE_WEIGHTS = (0.5, 0.0, 0.5)  # possession, field tilt, completion gap (tilt too noisy)
SMOOTHING = 0.6  # EMA weight on the newest minute; 1.0 = no smoothing


def _clip01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def dominance_index(
    w: WindowMetrics, weights: tuple[float, float, float] = DOMINANCE_WEIGHTS
) -> float:
    h, a = w.home, w.away
    wp, wt, wc = weights
    d = (
        wp * (h.possession_share - 0.5) * 2
        + wt * (h.field_tilt - 0.5) * 2
        + wc * (h.pass_completion - a.pass_completion) * 2
    )
    return round(max(-1.0, min(1.0, d)), 3)


def chaos_index(w: WindowMetrics) -> float:
    completion = (w.home.pass_completion + w.away.pass_completion) / 2
    c = 0.5 * _clip01((w.turnovers_per_min - 2.0) / 3.5) + 0.5 * _clip01((0.82 - completion) / 0.27)
    return round(c, 3)


def classify(
    dominance: float,
    chaos: float,
    current: State = "balanced",
    dominance_threshold: float = DOMINANCE_THRESHOLD,
    chaos_threshold: float = CHAOS_THRESHOLD,
    stickiness: float = STICKINESS,
) -> State:
    """Schmitt-trigger classification: entering a state needs the full threshold,
    staying in it only `stickiness` x the threshold. This removes flicker at the edges."""
    c_in = chaos_threshold * (stickiness if current == "chaos" else 1.0)
    if chaos >= c_in:
        return "chaos"
    d_home = dominance_threshold * (stickiness if current == "home_control" else 1.0)
    d_away = dominance_threshold * (stickiness if current == "away_control" else 1.0)
    if dominance >= d_home:
        return "home_control"
    if dominance <= -d_away:
        return "away_control"
    return "balanced"


class PulseSnapshot(BaseModel):
    kind: Literal["snapshot"] = "snapshot"
    minute: int
    dominance: float
    chaos: float
    raw_state: State
    state: State
    window: WindowMetrics


class Transition(BaseModel):
    kind: Literal["transition"] = "transition"
    id: str
    detected_minute: int
    estimated_minute: float
    from_state: State
    to_state: State
    before: WindowMetrics
    after: WindowMetrics
    evidence: list[str]


PulseOutput = PulseSnapshot | Transition


class MatchPulse:
    def __init__(
        self,
        meta: MatchMeta | None = None,
        window: int = 5,
        confirm: int = 3,
        dominance_threshold: float = DOMINANCE_THRESHOLD,
        chaos_threshold: float = CHAOS_THRESHOLD,
        stickiness: float = STICKINESS,
        weights: tuple[float, float, float] = DOMINANCE_WEIGHTS,
        smoothing: float = SMOOTHING,
    ):
        self.meta = meta
        self.weights = weights
        self.smoothing = smoothing
        self._dom_ema: float | None = None
        self._chaos_ema: float | None = None
        self.window = window
        self.confirm = confirm
        self.dominance_threshold = dominance_threshold
        self.chaos_threshold = chaos_threshold
        self.stickiness = stickiness
        self.counter = MinuteCounter()
        self.state: State = "balanced"
        self.state_since = 0
        self.candidate: State | None = None
        self.candidate_since = 0
        self.candidate_count = 0
        self.next_minute = 0  # first minute not yet closed
        self.snapshots: list[PulseSnapshot] = []
        self.transitions: list[Transition] = []

    def ingest(self, ev: Event) -> list[PulseOutput]:
        """Add one event; return snapshots/transitions for any minutes that just closed."""
        out: list[PulseOutput] = []
        while ev.minute > self.next_minute:
            out.extend(self._close_minute(self.next_minute))
            self.next_minute += 1
        self.counter.ingest(ev)
        if ev.type == EventType.HALF_END and ev.period == 2:
            out.extend(self.finish())
        return out

    def finish(self) -> list[PulseOutput]:
        out: list[PulseOutput] = []
        while self.next_minute <= self.counter.max_minute:
            out.extend(self._close_minute(self.next_minute))
            self.next_minute += 1
        return out

    def _close_minute(self, minute: int) -> list[PulseOutput]:
        w = self.counter.window(minute, self.window)
        dom, chaos = dominance_index(w, self.weights), chaos_index(w)
        a = self.smoothing
        if self._dom_ema is not None:
            dom = round(a * dom + (1 - a) * self._dom_ema, 3)
            chaos = round(a * chaos + (1 - a) * self._chaos_ema, 3)
        self._dom_ema, self._chaos_ema = dom, chaos
        raw = classify(
            dom, chaos, self.state,
            self.dominance_threshold, self.chaos_threshold, self.stickiness,
        )
        out: list[PulseOutput] = []

        if minute + 1 < self.window:  # not enough history yet: hold the opening state
            raw_effective: State = self.state
        else:
            raw_effective = raw

        if raw_effective == self.state:
            self.candidate, self.candidate_count = None, 0
        elif raw_effective == self.candidate:
            self.candidate_count += 1
        else:
            self.candidate, self.candidate_since, self.candidate_count = raw_effective, minute, 1

        if self.candidate is not None and self.candidate_count >= self.confirm:
            before_end = max(self.candidate_since - 1, 0)
            before = self.counter.window(before_end, self.window)
            t = Transition(
                id=f"tr-{len(self.transitions) + 1:02d}",
                detected_minute=minute,
                estimated_minute=max(0.0, self.candidate_since - self.window / 2),
                from_state=self.state,
                to_state=self.candidate,
                before=before,
                after=w,
                evidence=w.evidence,
            )
            self.transitions.append(t)
            out.append(t)
            self.state, self.state_since = self.candidate, self.candidate_since
            self.candidate, self.candidate_count = None, 0

        snap = PulseSnapshot(
            minute=minute, dominance=dom, chaos=chaos, raw_state=raw, state=self.state, window=w
        )
        self.snapshots.append(snap)
        out.append(snap)
        return out


def run_pulse(events: list[Event], meta: MatchMeta | None = None, **kw) -> MatchPulse:
    pulse = MatchPulse(meta, **kw)
    for ev in events:
        pulse.ingest(ev)
    pulse.finish()
    return pulse

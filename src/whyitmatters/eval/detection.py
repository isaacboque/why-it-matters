"""Score the Match Pulse engine against the simulator's planted ground truth."""

from __future__ import annotations

from dataclasses import dataclass

from whyitmatters.pulse import run_pulse
from whyitmatters.schema import Match
from whyitmatters.simulator.phases import phase_at

TOLERANCE_MINUTES = 4.0


@dataclass
class MatchScore:
    match_id: str
    true_shifts: int
    detected: int
    hits: int
    minute_accuracy: float
    timeline_accuracy: float
    mean_lag: float | None

    @property
    def precision(self) -> float:
        return self.hits / self.detected if self.detected else 1.0

    @property
    def recall(self) -> float:
        return self.hits / self.true_shifts if self.true_shifts else 1.0


def score_match(match: Match, tolerance: float = TOLERANCE_MINUTES) -> MatchScore:
    pulse = run_pulse(match.events, match.meta)
    truth = match.truth.phases
    shifts = [(p.start_minute, p.kind) for p in truth[1:]]

    used: set[int] = set()
    hits, lags = 0, []
    for tr in pulse.transitions:
        best, best_gap = None, None
        for i, (minute, kind) in enumerate(shifts):
            gap = abs(tr.estimated_minute - minute)
            if i in used or kind != tr.to_state or gap > tolerance:
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = i, gap
        if best is not None:
            used.add(best)
            hits += 1
            lags.append(tr.detected_minute - shifts[best][0])

    total = correct = 0
    for snap in pulse.snapshots:
        if snap.minute >= 90:
            continue
        total += 1
        correct += snap.state == phase_at(truth, snap.minute + 0.5).kind

    # Timeline accuracy: the state history the recap reports, with each change back-dated
    # to its estimated start (what an analyst says after the fact: "since the 13th minute").
    timeline = [(0.0, "balanced")] + [(t.estimated_minute, t.to_state) for t in pulse.transitions]
    t_total = t_correct = 0
    for minute in range(90):
        state = [s for start, s in timeline if start <= minute + 0.5][-1]
        t_total += 1
        t_correct += state == phase_at(truth, minute + 0.5).kind

    return MatchScore(
        match_id=match.meta.match_id,
        true_shifts=len(shifts),
        detected=len(pulse.transitions),
        hits=hits,
        minute_accuracy=correct / total if total else 0.0,
        timeline_accuracy=t_correct / t_total,
        mean_lag=sum(lags) / len(lags) if lags else None,
    )


@dataclass
class Summary:
    matches: int
    precision: float
    recall: float
    minute_accuracy: float
    timeline_accuracy: float
    mean_lag: float

    def as_dict(self) -> dict[str, float]:
        return {
            "matches": self.matches,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "minute_accuracy": round(self.minute_accuracy, 3),
            "timeline_accuracy": round(self.timeline_accuracy, 3),
            "mean_detection_lag_min": round(self.mean_lag, 2),
        }


def summarize(scores: list[MatchScore]) -> Summary:
    hits = sum(s.hits for s in scores)
    detected = sum(s.detected for s in scores)
    shifts = sum(s.true_shifts for s in scores)
    lags = [s.mean_lag for s in scores if s.mean_lag is not None]
    return Summary(
        matches=len(scores),
        precision=hits / detected if detected else 1.0,
        recall=hits / shifts if shifts else 1.0,
        minute_accuracy=sum(s.minute_accuracy for s in scores) / len(scores),
        timeline_accuracy=sum(s.timeline_accuracy for s in scores) / len(scores),
        mean_lag=sum(lags) / len(lags) if lags else 0.0,
    )

"""Driver attribution: why did control change hands?

When the Match Pulse confirms that a team has taken control, compare the window before the
shift with the window after it and name the 2-3 tactical metrics that moved most in that
team's favour. Each change is normalised by what is a big move for that metric (about the
90th percentile of window-to-window changes over seeds 0-19), so a PPDA drop of 6 and a rise
of 3 high recoveries can be ranked against each other. Every driver then travels as a
`Claim`, so the Verifier checks it like any other number.
"""

from __future__ import annotations

from dataclasses import dataclass

from whyitmatters.agents.models import Claim, Unit
from whyitmatters.pulse.engine import Transition
from whyitmatters.pulse.metrics import TeamWindow, WindowMetrics
from whyitmatters.schema import Side

MAX_DRIVERS = 3
MIN_SCORE = 0.3  # share of a "big move" a change must reach to count as a driver
MIN_DUELS = 3  # a duel share over fewer duels than this is noise
PPDA_CAP = 20.0  # "never made a defensive action" counts as this PPDA in a head-to-head gap
HEAD_TO_HEAD = 1.5  # a gap moves about this much more than one team's own number
MIN_POSSESSION = 0.15  # floor when restating a count per opportunity


@dataclass(frozen=True)
class DriverSpec:
    metric: str
    unit: Unit
    mine: bool  # True: the subject team's own number; False: the opponent's
    direction: int  # +1: higher helps the subject team, -1: lower helps (PPDA)
    scale: float  # what counts as a big move
    tolerance: float
    tags: tuple[str, ...]
    # the number the text states must be worth saying: at least `floor` (at most, for PPDA)
    floor: float = 0.0
    # defensive counts only happen while the other team has the ball, so a team that hogs it has
    # fewer chances to press: rank them per opportunity (see _advantage)
    per_opportunity: bool = False
    # a style choice (going long), not a gap: only the team's own rise counts
    own_only: bool = False

    def worth_stating(self, value: float) -> bool:
        return value <= self.floor if self.direction < 0 else value >= self.floor


DRIVERS: dict[str, DriverSpec] = {
    "duel_mid": DriverSpec("duel_share_mid", "share", True, 1, 0.5, 0.006, ("duels",), 0.55),
    "duel_att": DriverSpec(
        "duel_share_att", "share", True, 1, 0.5, 0.006, ("duels", "pressing"), 0.55
    ),
    "pressures": DriverSpec(
        "pressures", "count", True, 1, 10.0, 0.0, ("pressing",), 5, per_opportunity=True
    ),
    "high_rec": DriverSpec(
        "high_recoveries", "count", True, 1, 4.0, 0.0, ("pressing",), 2, per_opportunity=True
    ),
    "final_rec": DriverSpec(
        "final_third_recoveries",
        "count",
        True,
        1,
        3.0,
        0.0,
        ("pressing",),
        2,
        per_opportunity=True,
    ),  # fmt: skip
    "counter_press": DriverSpec(
        "counter_press", "count", True, 1, 3.0, 0.0, ("pressing",), 2, per_opportunity=True
    ),
    "ppda": DriverSpec("ppda", "rate", True, -1, 10.0, 0.06, ("pressing",), 8.0),
    "opp_losses": DriverSpec(
        "own_half_losses", "count", False, 1, 5.0, 0.0, ("pressing",), 3, per_opportunity=True
    ),
    "progressive": DriverSpec(
        "progressive_passes", "count", True, 1, 6.0, 0.0, ("pass_quality",), 5
    ),
    "long_ball": DriverSpec(
        "long_ball_share", "share", True, 1, 0.12, 0.006, ("pass_quality",), 0.12, own_only=True
    ),
}

# Which drivers say "pressing" (the simulator's DOMINANT style presses; see tests)
PRESS_DRIVERS = frozenset(k for k, s in DRIVERS.items() if "pressing" in s.tags)


@dataclass(frozen=True)
class Driver:
    key: str
    side: Side  # whose window the value is read from
    before: float
    after: float
    score: float  # normalised change in the subject team's favour

    @property
    def spec(self) -> DriverSpec:
        return DRIVERS[self.key]


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


def _team(w: WindowMetrics, side: Side) -> TeamWindow:
    return w.home if side == "home" else w.away


def _enough_duels(key: str, after: WindowMetrics, side: Side) -> bool:
    me, opp = _team(after, side), _team(after, _other(side))
    if key == "duel_mid":
        return me.duels_won_mid + opp.duels_won_mid >= MIN_DUELS
    if key == "duel_att":
        return me.duels_won_att + opp.duels_won_def >= MIN_DUELS
    return True


def _advantage(
    w: WindowMetrics, spec: DriverSpec, subject: Side, baseline: bool = False
) -> float | None:
    """How far `subject` is ahead of the other side on a metric in one window.

    Counts and rates are compared head to head (my high recoveries minus theirs; PPDA with the
    sign flipped, and "no defensive action at all" counted as PPDA_CAP); duel shares are already
    head to head; `opp_losses` is the opponent's own-half losses minus ours.
    """
    me, opp = _team(w, subject), _team(w, _other(subject))
    if spec.metric.startswith("duel_share"):
        share = getattr(me, spec.metric)
        if share is None:  # nobody won a duel there: a neutral baseline, but nothing to state
            return 0.5 if baseline else None
        return float(share)
    if spec.metric == "ppda":
        mine = PPDA_CAP if me.ppda is None else me.ppda
        theirs = PPDA_CAP if opp.ppda is None else opp.ppda
        return theirs - mine  # a lower PPDA is the better press
    if spec.own_only:
        return float(getattr(me, spec.metric))
    if spec.per_opportunity:
        # a count that can only happen while the other team has the ball, restated as if the
        # other team had had half of it (so 50/50 possession leaves the raw count unchanged)
        def adj(count: int, other_possession: float) -> float:
            return count * 0.5 / max(other_possession, MIN_POSSESSION)

        if spec.mine:
            mine = adj(getattr(me, spec.metric), opp.possession_share)
            theirs = adj(getattr(opp, spec.metric), me.possession_share)
            return mine - theirs
        # opp_losses: their own-half losses happen on their ball, ours on ours
        return adj(getattr(opp, spec.metric), opp.possession_share) - adj(
            getattr(me, spec.metric), me.possession_share
        )
    if spec.mine:
        return float(getattr(me, spec.metric) - getattr(opp, spec.metric))
    return float(getattr(opp, spec.metric) - getattr(me, spec.metric))


def rank_drivers(before: WindowMetrics, after: WindowMetrics, subject: Side) -> list[Driver]:
    """The metrics that moved most in `subject`'s favour between two windows, best first.

    "Moved" is the change in the head-to-head gap, so a team that starts pressing and an
    opponent that stops both count. The claim states the subject's (or, for `opp_losses`, the
    opponent's) own number in the after window.
    """
    out: list[Driver] = []
    for key, spec in DRIVERS.items():
        side = subject if spec.mine else _other(subject)
        a_now = _advantage(after, spec, subject)
        a_was = _advantage(before, spec, subject, baseline=True)
        stated = getattr(_team(after, side), spec.metric)
        if a_now is None or a_was is None or stated is None or not spec.worth_stating(stated):
            continue
        if not _enough_duels(key, after, subject):
            continue
        gap_scale = spec.scale * (1.0 if spec.metric.startswith("duel_share") else HEAD_TO_HEAD)
        score = (a_now - a_was) / gap_scale
        if score >= MIN_SCORE:
            was = getattr(_team(before, side), spec.metric)
            out.append(Driver(key, side, float(was or 0.0), float(stated), round(score, 3)))
    out.sort(key=lambda d: (-d.score, d.key))
    return out[:MAX_DRIVERS]


def drivers_of(tr: Transition, subject: Side) -> list[Driver]:
    return rank_drivers(tr.before, tr.after, subject)


def driver_claims(drivers: list[Driver], window: tuple[int, int]) -> list[Claim]:
    """One claim per driver, keyed dv1, dv2, ... in rank order."""
    return [
        Claim(
            key=f"dv{i}",
            metric=d.spec.metric,  # type: ignore[arg-type]
            unit=d.spec.unit,
            side=d.side,
            value=d.after,
            window=window,
            tolerance=d.spec.tolerance,
        )
        for i, d in enumerate(drivers, start=1)
    ]

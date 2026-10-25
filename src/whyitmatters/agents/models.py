"""Typed messages passed between agents.

Every number an agent puts on screen travels as a `Claim`, so the Verifier can check it
against the Blackboard and the Personalizer can prove it invented nothing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from whyitmatters.schema import Side

Lang = str  # any BCP-47 code ("en", "pt-BR", "ja"); en / es / ca have offline templates
Mode = Literal["analyst", "fan", "player_focus", "coach"]

InsightKind = Literal[
    "state_shift",  # Match Pulse confirmed a change of who controls the game
    "goal",
    "big_chance",  # missed chance with xG >= 0.3
    "top_speed",  # new fastest carry of the match
    "pass_master",  # a player reaches a completed-pass milestone
    "press_surge",  # a team's pressing jumps: high recoveries, low PPDA
    "midfield_battle",  # a team wins most of the midfield duels
    "danger_turnovers",  # a team keeps losing the ball in its own half
    "direct_switch",  # a team goes long to bypass the press
    "pass_difficulty",  # hardest completed pass of the match so far
    "shot_speed",  # fastest shot of the match so far
]

# Metrics a viewer can follow on their own ("My metric" in the Fan tab)
MetricTag = Literal["pressing", "duels", "possession", "xg", "pass_quality", "speed"]
METRIC_TAGS: tuple[str, ...] = ("pressing", "duels", "possession", "xg", "pass_quality", "speed")

Metric = Literal[
    "possession_share",  # window, side
    "pass_completion",  # window, side
    "field_tilt",  # window, side
    "turnovers_per_min",  # window, both sides
    "window_minutes",  # window length
    "shot_xg",  # event
    "score_home",  # event (score after it)
    "score_away",  # event
    "player_completed_passes",  # player, as of event
    "carry_speed_kmh",  # event
    "team_xg",  # side, whole match as of event
    # tactical, window + side (pulse/metrics.py TeamWindow fields)
    "duel_share_def",
    "duel_share_mid",
    "duel_share_att",
    "duels_won_mid",
    "high_recoveries",
    "final_third_recoveries",
    "counter_press",
    "own_half_losses",
    "progressive_passes",
    "long_ball_share",
    "central_buildup_share",
    "ppda",
    "pressures",
    # event based
    "pass_difficulty",  # event: difficulty of a completed pass
    "shot_speed_kmh",  # event: ball speed of a shot
    "buildup_seconds",  # shot event: seconds from winning the ball to the shot
    "counter_press_in_move",  # shot event: 1 if the move began with a counter-press recovery
    "long_balls_in_move",  # shot event: completed long balls in the move
    # value and shape from freeze frames, window + side (pulse/xt.py, pulse/shape.py)
    "xt",  # Expected Threat added by completed passes and carries
    "line_height",  # out-of-possession back line, metres from own goal
    "line_height_in",
    "gap_def_mid",  # metres between the back line and the next line (out of possession)
    "gap_mid_att",
    "team_length",
    "team_width",
    "compactness",  # convex hull area of the outfield players, m^2
    "formation_out",  # formation code, e.g. 442 for "4-4-2"
    "formation_in",
]

# Claim metrics read straight off a team's rolling window
TEAM_WINDOW_METRICS = frozenset(
    {
        "possession_share",
        "pass_completion",
        "field_tilt",
        "duel_share_def",
        "duel_share_mid",
        "duel_share_att",
        "duels_won_mid",
        "high_recoveries",
        "final_third_recoveries",
        "counter_press",
        "own_half_losses",
        "progressive_passes",
        "long_ball_share",
        "central_buildup_share",
        "ppda",
        "pressures",
        "xt",
        "line_height",
        "line_height_in",
        "gap_def_mid",
        "gap_mid_att",
        "team_length",
        "team_width",
        "compactness",
        "formation_out",
        "formation_in",
    }
)

Unit = Literal[
    "share", "count", "xg", "kmh", "rate", "minutes", "index", "seconds",
    "metres", "m2", "formation", "xt",
]


class Claim(BaseModel):
    key: str  # slot name the number fills in the text, e.g. "poss"
    metric: Metric
    value: float
    unit: Unit
    side: Side | None = None
    player_id: str | None = None
    event_id: str | None = None
    window: tuple[int, int] | None = None  # inclusive start/end match minute
    tolerance: float = 0.0


class InsightCandidate(BaseModel):
    id: str
    kind: InsightKind
    minute: int
    t: float  # match seconds the insight refers to
    significance: float = Field(ge=0, le=1)
    side: Side | None = None
    player_id: str | None = None
    event_id: str | None = None
    transition_id: str | None = None
    to_state: str | None = None
    from_state: str | None = None
    window: tuple[int, int] | None = None  # tactical insights: the rolling window they describe
    evidence: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    """Explainer output: words plus the claims behind every number in them."""

    candidate_id: str
    attempt: int
    headline: str
    body: str
    claims: list[Claim]
    slots: dict[str, str] = Field(default_factory=dict)  # words: team, player, variant


class ClaimCheck(BaseModel):
    claim: Claim
    actual: float | None
    ok: bool
    reason: str | None = None


class Verdict(BaseModel):
    candidate_id: str
    attempt: int
    ok: bool
    checks: list[ClaimCheck]
    unsupported_numbers: list[str] = Field(default_factory=list)
    unsupported_names: list[str] = Field(
        default_factory=list
    )  # known teams / players not in the brief

    @property
    def failures(self) -> list[ClaimCheck]:
        return [c for c in self.checks if not c.ok]


class Insight(BaseModel):
    """A verified insight, ready for the Producer."""

    id: str
    kind: InsightKind
    minute: int
    t: float
    significance: float
    side: Side | None
    player_id: str | None
    headline: str
    body: str
    claims: list[Claim]
    slots: dict[str, str]
    evidence: list[str]
    attempts: int
    latency_ms: float
    tags: list[str] = Field(default_factory=list)  # which "My metric" threads it belongs to


class Cue(BaseModel):
    """Timed overlay cue a graphics partner can render on a live feed."""

    cue_id: str
    insight_id: str
    kind: InsightKind
    t_in: float  # match seconds
    t_out: float
    minute: int
    priority: int  # 1 = highest
    headline: str
    body: str
    side: Side | None
    player_id: str | None
    evidence_event_ids: list[str]
    claims: list[Claim]
    slots: dict[str, str] = Field(default_factory=dict)
    verified: bool = True
    tags: list[str] = Field(default_factory=list)


class Viewer(BaseModel):
    mode: Mode = "analyst"
    lang: Lang = "en"
    club: Side | None = None  # favourite club
    player_id: str | None = None  # favourite / focus player
    metric: MetricTag | None = None  # follow one thread only (goals always show)


class PersonalCue(BaseModel):
    """A cue as one viewer sees it."""

    cue_id: str
    kind: InsightKind
    t_in: float
    t_out: float
    minute: int
    priority: int
    headline: str
    body: str
    for_you: bool  # involves the viewer's club or player
    evidence_event_ids: list[str]
    claims: list[Claim]
    verified: bool
    tags: list[str] = Field(default_factory=list)
    written_by: str = "template"  # "model" | "template" | "template_fallback"
    translation_unavailable: bool = False  # the text is English because the language has no writer


class RecapMoment(BaseModel):
    minute: int
    headline: str
    body: str
    evidence_event_ids: list[str]


class Recap(BaseModel):
    headline: str
    score_home: int
    score_away: int
    summary: str
    moments: list[RecapMoment]
    claims: list[Claim]
    written_by: str = "template"
    translation_unavailable: bool = False
    slots: dict[str, str] = Field(default_factory=dict)  # names the recap may mention


class TrustStats(BaseModel):
    claims_generated: int = 0  # every claim in every draft, all attempts
    claims_verified: int = 0
    first_drafts: int = 0
    first_drafts_ok: int = 0
    retries: int = 0
    dropped: int = 0  # candidates that never passed verification
    personalized_checked: int = 0
    personalized_rejected: int = 0

    @property
    def truth_score(self) -> float:
        """Share of all generated claims that matched the match state."""
        return self.claims_verified / self.claims_generated if self.claims_generated else 1.0

    @property
    def first_draft_accuracy(self) -> float:
        return self.first_drafts_ok / self.first_drafts if self.first_drafts else 1.0

    def as_dict(self) -> dict[str, float]:
        return {
            "truth_score": round(self.truth_score, 3),
            "first_draft_accuracy": round(self.first_draft_accuracy, 3),
            "claims_generated": self.claims_generated,
            "claims_verified": self.claims_verified,
            "retries": self.retries,
            "dropped": self.dropped,
            "on_air_accuracy": 1.0,  # nothing airs unverified; the end-of-match audit re-checks
        }

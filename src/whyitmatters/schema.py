"""Data contract shared by every stage of the pipeline.

Coordinates are metres on a 105 x 68 pitch from the acting team's perspective:
every team attacks left to right (x 0 -> 105). Time is match seconds from kick-off.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

Side = Literal["home", "away"]


class EventType(StrEnum):
    KICK_OFF = "kick_off"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    PRESSURE = "pressure"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    BALL_OUT = "ball_out"
    HALF_END = "half_end"


class Outcome(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    GOAL = "goal"
    SAVED = "saved"
    OFF_TARGET = "off_target"
    BLOCKED = "blocked"
    WON = "won"
    LOST = "lost"


class Player(BaseModel):
    id: str
    name: str
    number: int
    position: str
    side: Side


class Team(BaseModel):
    id: str
    name: str
    short_name: str
    side: Side
    formation: str
    players: list[Player]


class MatchMeta(BaseModel):
    match_id: str
    seed: int
    competition: str = "Synthetic League"
    venue: str
    kickoff_local: str
    home: Team
    away: Team


class Freeze(BaseModel):
    """Where all 22 players stand at an event, in the ACTING team's coordinates.

    `t` = the acting team's players, `o` = the opponents, each in its team's `players` order.
    """

    t: list[tuple[float, float]]
    o: list[tuple[float, float]]


class Event(BaseModel):
    """One on-ball or defensive action."""

    id: str
    seq: int
    t: float = Field(description="Match seconds from kick-off")
    period: Literal[1, 2]
    minute: int
    type: EventType
    side: Side
    player_id: str | None = None
    possession_id: int
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    outcome: Outcome | None = None
    receiver_id: str | None = None
    under_pressure: bool = False
    # Pass quality
    pass_distance: float | None = None
    pass_difficulty: float | None = Field(default=None, description="0 easy .. 1 very hard")
    # Speed metrics (km/h)
    ball_speed_kmh: float | None = None
    # Shot quality
    xg: float | None = None
    score_home: int = 0
    score_away: int = 0
    # Positions of all 22 players at this event (StatsBomb-360-style freeze frame)
    freeze: Freeze | None = None


PhaseKind = Literal["home_control", "away_control", "chaos", "balanced"]


class Phase(BaseModel):
    kind: PhaseKind
    start_minute: float
    end_minute: float


class KeyMoment(BaseModel):
    kind: Literal["goal", "big_chance"]
    event_id: str
    minute: int
    side: Side
    xg: float


class ShapeTruth(BaseModel):
    """The shape a team was scripted to play during a phase."""

    side: Side
    start_minute: float
    end_minute: float
    in_possession: str  # formation label, back to front, e.g. "3-2-5"
    out_of_possession: str  # e.g. "4-4-2"
    block: Literal["high", "mid", "low"]


class GroundTruth(BaseModel):
    """Known answers the simulator planted. Never shown to the agents; evaluation only."""

    phases: list[Phase]
    key_moments: list[KeyMoment]
    shapes: list[ShapeTruth] = []


class Match(BaseModel):
    meta: MatchMeta
    events: list[Event]
    truth: GroundTruth

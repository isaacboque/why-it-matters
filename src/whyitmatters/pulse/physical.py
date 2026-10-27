"""Distance and speed from freeze frames.

Freeze frames exist only at ball events, so this is NOT continuous tracking. Each team keeps a
checkpoint (the frame at the last event at least CHECK_S seconds ago). When the next event is
at least CHECK_S and at most MAX_GAP_S later, in the same half and with no kick-off between,
every outfield player is credited the straight-line distance between the two checkpoints and
an average speed over that interval. The 4 s minimum keeps the frames' positional noise (about
1 m) from turning into fake speed; straight lines between checkpoints undercount the real path.
Values are comparable between teams, windows and minutes of the same simulator; they are not
comparable to a real tracking provider's totals.

A player who is the actor of an event (the freeze frame puts him exactly at the ball) may have
jumped to it, so a leg is dropped for any player who acted at an event since the checkpoint.

- distance: metres, summed over a team's 10 outfield players
- high-speed run: an interval whose average speed is at least HIGH_KMH
- sprint: an interval whose average speed is at least SPRINT_KMH (25 km/h, the hackathon rules'
  threshold for speed indicators)
- top speed: the largest interval speed, km/h
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from whyitmatters.pulse.shape import Pos, own_frame
from whyitmatters.schema import Event, EventType, Side

CHECK_S = 4.0
MAX_GAP_S = 15.0
HIGH_KMH = 20.0
SPRINT_KMH = 25.0
KMH = 3.6


@dataclass
class Leg:
    """One player's movement between two checkpoints."""

    index: int  # position in the team's players order (0 = goalkeeper, never reported)
    metres: float
    kmh: float


@dataclass
class Checkpoints:
    """Streams events and yields, per side, the legs completed at each event."""

    last: dict[Side, tuple[int, float, list[Pos]]] = field(default_factory=dict)
    acted: dict[Side, set[int]] = field(default_factory=dict)  # players on the ball since then

    def ingest(self, ev: Event) -> dict[Side, list[Leg]]:
        out: dict[Side, list[Leg]] = {}
        if ev.type in (EventType.HALF_END, EventType.KICK_OFF) or ev.freeze is None:
            self.last.clear()  # a kick-off re-spots the players; nothing to credit across it
            self.acted.clear()
            if ev.freeze is None:
                return out
        if ev.type != EventType.KICK_OFF:
            actors = self.acted.setdefault(ev.side, set())
            for i, (px, py) in enumerate(ev.freeze.t):
                if abs(px - ev.x) < 0.06 and abs(py - ev.y) < 0.06:
                    actors.add(i)
        for side in ("home", "away"):
            frame = own_frame(ev, side)
            if frame is None:
                continue
            prev = self.last.get(side)
            skip = self.acted.get(side, set())
            if prev is not None and prev[0] == ev.period:
                dt = ev.t - prev[1]
                if dt < CHECK_S:
                    continue  # keep the older checkpoint
                if dt <= MAX_GAP_S:
                    out[side] = [
                        Leg(i, d, d / dt * KMH)
                        for i, ((x0, y0), (x1, y1)) in enumerate(zip(prev[2], frame, strict=True))
                        if i > 0 and i not in skip and (d := math.hypot(x1 - x0, y1 - y0)) >= 0
                    ]
            self.last[side] = (ev.period, ev.t, frame)
            self.acted[side] = set()
        return out

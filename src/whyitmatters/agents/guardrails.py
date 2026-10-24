"""Checks every generated text must pass before it airs, besides the number check.

Numbers: `Verifier.unsupported_numbers` (every number must match a verified claim, formatted for
the language). Names, here: a known team or player that is not in the insight's brief means the
text invented a subject. Length: a caption has to fit a lower third.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from whyitmatters.agents.models import Mode
from whyitmatters.schema import MatchMeta

# characters, per mode (a headline is capped separately)
MAX_BODY_CHARS: dict[str, int] = {"analyst": 420, "fan": 300, "player_focus": 300, "coach": 520}
MAX_HEADLINE_CHARS = 90

NAME_SLOTS = ("home", "away", "team", "other", "player", "winner", "loser")


def brief_names(slots: Mapping[str, str]) -> set[str]:
    """The names an insight is allowed to mention: the ones in its slots."""
    return {slots[k] for k in NAME_SLOTS if slots.get(k)}


def known_names(meta: MatchMeta) -> tuple[list[str], list[str]]:
    """(team names, player names) of the match."""
    teams = [meta.home.name, meta.away.name]
    players = [p.name for team in (meta.home, meta.away) for p in team.players]
    return teams, players


def _mentions(name: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) is not None


def name_violations(
    text: str, allowed: Iterable[str], teams: Iterable[str], players: Iterable[str]
) -> list[str]:
    """Known teams or players that the text mentions although they are not in the brief.

    A player counts as mentioned by full name or by surname, unless that surname is also part
    of a name the brief allows (so a shared surname cannot raise a false alarm).
    """
    allowed_set = {a for a in allowed if a}
    allowed_tokens = {tok for a in allowed_set for tok in a.split()}
    bad: list[str] = [t for t in teams if t not in allowed_set and _mentions(t, text)]
    others = [p for p in players if p not in allowed_set]
    bad += [p for p in others if _mentions(p, text)]
    named_surnames = {p.split()[-1] for p in bad}  # already explained by a full-name hit
    for name in others:
        surname = name.split()[-1]
        if (
            name not in bad
            and len(surname) > 2
            and surname not in allowed_tokens
            and surname not in named_surnames
            and _mentions(surname, text)
        ):
            bad.append(name)
    return bad


def length_problem(headline: str, body: str, mode: Mode) -> str | None:
    limit = MAX_BODY_CHARS.get(mode, 300)
    if len(body) > limit:
        return f"body is {len(body)} characters, the limit for {mode} is {limit}"
    if len(headline) > MAX_HEADLINE_CHARS:
        return f"headline is {len(headline)} characters, the limit is {MAX_HEADLINE_CHARS}"
    if not headline.strip() or not body.strip():
        return "headline and body must both be non-empty"
    return None

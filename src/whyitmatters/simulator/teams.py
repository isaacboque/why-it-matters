"""Fictional clubs and players. Nothing here refers to a real club or person."""

from __future__ import annotations

import random

from whyitmatters.schema import Player, Side, Team

CLUBS = [
    ("Northbridge Athletic", "NBA"),
    ("Harbor City", "HBC"),
    ("Ravenmoor United", "RVM"),
    ("Kingsford Rovers", "KFR"),
    ("Ashvale Town", "ASH"),
    ("Westholm Albion", "WHA"),
    ("Corrin Bay", "CRB"),
    ("Elmstead Wanderers", "ELW"),
]

VENUES = ["Riverside Park", "The Foundry Ground", "Millgate Stadium", "Harbourfront Arena"]

FIRST = [
    "Aron", "Bram", "Cael", "Dario", "Emil", "Fenn", "Goran", "Hugo", "Ivo", "Jory",
    "Kasim", "Lio", "Mato", "Niko", "Oren", "Pau", "Quin", "Rafe", "Soren", "Teo",
    "Ulric", "Vito", "Wes", "Yann", "Zeno", "Ander", "Bastien", "Ciro", "Dane", "Eloy",
]
LAST = [
    "Ashworth", "Brennick", "Calloway", "Dravic", "Esterby", "Falkner", "Garrow", "Holm",
    "Isard", "Jessop", "Kerrigan", "Lindqvist", "Morrow", "Nantes", "Okafor", "Petrell",
    "Quarry", "Rossiter", "Sallow", "Thorne", "Underhill", "Valcourt", "Wexley", "Yarrow",
    "Zielin", "Abernath", "Blackwood", "Corvel", "Dunmore", "Everly",
]

# 4-3-3: position, shirt number, nominal x (own perspective), nominal y
FORMATION_433 = [
    ("GK", 1, 5.0, 34.0),
    ("RB", 2, 30.0, 60.0),
    ("CB", 4, 22.0, 44.0),
    ("CB", 5, 22.0, 24.0),
    ("LB", 3, 30.0, 8.0),
    ("DM", 6, 40.0, 34.0),
    ("CM", 8, 52.0, 48.0),
    ("CM", 10, 55.0, 20.0),
    ("RW", 7, 78.0, 60.0),
    ("ST", 9, 85.0, 34.0),
    ("LW", 11, 78.0, 8.0),
]

NOMINAL = {f"{pos}{num}": (x, y) for pos, num, x, y in FORMATION_433}


def make_team(rng: random.Random, club: tuple[str, str], side: Side) -> Team:
    name, short = club
    used: set[str] = set()
    players: list[Player] = []
    for pos, num, _, _ in FORMATION_433:
        while True:
            full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if full not in used:
                used.add(full)
                break
        players.append(
            Player(id=f"{short.lower()}-{num}", name=full, number=num, position=pos, side=side)
        )
    return Team(
        id=short.lower(), name=name, short_name=short, side=side, formation="4-3-3",
        players=players,
    )


def nominal_xy(player: Player) -> tuple[float, float]:
    return NOMINAL[f"{player.position}{player.number}"]

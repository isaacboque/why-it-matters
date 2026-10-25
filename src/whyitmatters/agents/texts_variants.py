# ruff: noqa: E501  (sentences read better unbroken)
"""Second and third wordings for the insights viewers see most, plus game-situation phrases.

A 90-minute match produces several cues of the same kind (seven control shifts is normal), and
reading the same sentence each time sounds like a machine. The Explainer rotates through the
wordings per template; every wording uses the same claim keys, so the Verifier checks exactly
the same numbers. Same conventions as texts_tactics.py: no digit in any static text.
"""

from __future__ import annotations

Alt = dict[str, dict[str, list[tuple[str, str]]]]

VARIANTS: dict[str, Alt] = {
    "goal": {
        "fan": {
            "en": [
                ("{player} scores!", "Get in! {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
                ("It's in! {player}!", "{player} finds the net for {team}: {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
            ],
            "es": [
                ("¡Marca {player}!", "¡Dentro! {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
                ("¡Gol de {player}!", "{player} marca para {team}: {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
            ],
            "ca": [
                ("Marca {player}!", "A dins! {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
                ("Gol de {player}!", "{player} marca per a {team}: {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
            ],
        },
    },
    "big_chance": {
        "fan": {
            "en": [
                ("What a miss!", "{player} had a great chance for {team}: shots like that go in {#xgpct} of the time."),
                ("{team} let one slip", "That was a big one for {player}: {#xgpct} of chances like it end up in the net."),
            ],
            "es": [
                ("¡Qué fallo!", "{player} tuvo una gran ocasión para {team}: tiros así acaban en gol el {#xgpct} de las veces."),
                ("Se le escapa a {team}", "Esa era clara para {player}: el {#xgpct} de ocasiones así acaban en gol."),
            ],
            "ca": [
                ("Quina errada!", "{player} ha tingut una gran ocasió per a {team}: xuts així acaben en gol el {#xgpct} de les vegades."),
                ("Se li escapa a {team}", "Aquesta era clara per a {player}: el {#xgpct} d'ocasions així acaben en gol."),
            ],
        },
    },
    "shift_control_why": {
        "fan": {
            "en": [
                ("{team} have taken over", "The game is going {team}'s way: {cause} in the last {#win} minutes."),
                ("{team} turn the screw", "{team} are calling the shots now: {cause} in the last {#win} minutes."),
            ],
            "es": [
                ("{team} se hace con el partido", "El partido va hacia {team}: {cause} en los últimos {#win} minutos."),
                ("{team} aprieta", "Ahora manda {team}: {cause} en los últimos {#win} minutos."),
            ],
            "ca": [
                ("{team} es fa amb el partit", "El partit va cap a {team}: {cause} en els últims {#win} minuts."),
                ("{team} estreny", "Ara mana {team}: {cause} en els últims {#win} minuts."),
            ],
        },
        "analyst": {
            "en": [
                ("Control swings to {team}", "Over the last {#win} minutes {team} have taken charge: {cause}. They have {#poss} of the ball and complete {#comp} of their passes."),
            ],
            "es": [
                ("El control pasa a {team}", "En los últimos {#win} minutos {team} ha tomado el mando: {cause}. Tiene el {#poss} del balón y completa el {#comp} de sus pases."),
            ],
            "ca": [
                ("El control passa a {team}", "En els últims {#win} minuts {team} ha pres el comandament: {cause}. Té el {#poss} de la pilota i completa el {#comp} de les passades."),
            ],
        },
    },
    "shift_chaos": {
        "fan": {
            "en": [
                ("It's all gone wild", "The ball is changing hands {#turn} times a minute. Neither side can calm it down."),
                ("Pinball out there", "{#turn} changes of possession a minute: it's frantic and anyone could score."),
            ],
            "es": [
                ("Se ha vuelto loco", "El balón cambia de dueño {#turn} veces por minuto. Nadie consigue calmarlo."),
                ("Esto es un pinball", "{#turn} cambios de posesión por minuto: es frenético y cualquiera puede marcar."),
            ],
            "ca": [
                ("S'ha tornat boig", "La pilota canvia de mans {#turn} vegades per minut. Ningú aconsegueix calmar-ho."),
                ("Això és un pinball", "{#turn} canvis de possessió per minut: és frenètic i qualsevol pot marcar."),
            ],
        },
        "analyst": {
            "en": [
                ("Structure has gone", "Possession is changing hands {#turn} times a minute over the last {#win} minutes. Transitions, not build-up, will decide the next spell."),
            ],
            "es": [
                ("Se ha perdido el orden", "La posesión cambia de manos {#turn} veces por minuto en los últimos {#win} minutos. Las transiciones, no la elaboración, decidirán el próximo tramo."),
            ],
            "ca": [
                ("S'ha perdut l'ordre", "La possessió canvia de mans {#turn} vegades per minut en els últims {#win} minuts. Les transicions, no l'elaboració, decidiran el proper tram."),
            ],
        },
    },
    "shift_balanced": {
        "fan": {
            "en": [
                ("All square out there", "It's even again: over the last {#win} minutes {home} have had the ball {#poss_h} of the time, {away} {#poss_a}."),
            ],
            "es": [
                ("Todo igualado", "Vuelve la igualdad: en los últimos {#win} minutos {home} ha tenido el balón el {#poss_h} del tiempo y {away} el {#poss_a}."),
            ],
            "ca": [
                ("Tot igualat", "Torna la igualtat: en els últims {#win} minuts {home} ha tingut la pilota el {#poss_h} del temps i {away} el {#poss_a}."),
            ],
        },
        "analyst": {
            "en": [
                ("Back to a balanced game", "The edge has gone. Over the last {#win} minutes possession is {home} {#poss_h}, {away} {#poss_a}, with no side completing clearly more passes."),
            ],
            "es": [
                ("Vuelve el equilibrio", "Se acabó la ventaja. En los últimos {#win} minutos la posesión es {home} {#poss_h}, {away} {#poss_a}, sin que nadie complete claramente más pases."),
            ],
            "ca": [
                ("Torna l'equilibri", "S'ha acabat l'avantatge. En els últims {#win} minuts la possessió és {home} {#poss_h}, {away} {#poss_a}, sense que ningú completi clarament més passades."),
            ],
        },
    },
    "press_surge": {
        "fan": {
            "en": [
                ("{team} won't let them breathe", "{team} have won the ball back in {other}'s half {#hr} times in the last {#win} minutes."),
            ],
            "es": [
                ("{team} no deja respirar", "{team} ha recuperado el balón en campo de {other} {#hr} veces en los últimos {#win} minutos."),
            ],
            "ca": [
                ("{team} no deixa respirar", "{team} ha recuperat la pilota al camp de {other} {#hr} vegades en els últims {#win} minuts."),
            ],
        },
    },
    "shape_change": {
        "fan": {
            "en": [
                ("A tactical tweak from {team}", "{team} look different on the ball: a {#now} now, where they were a {#was}."),
            ],
            "es": [
                ("Retoque táctico de {team}", "{team} se ve distinto con balón: ahora un {#now}, donde antes era un {#was}."),
            ],
            "ca": [
                ("Retoc tàctic de {team}", "{team} es veu diferent amb pilota: ara un {#now}, on abans era un {#was}."),
            ],
        },
    },
    "line_breakers": {
        "fan": {
            "en": [
                ("{team} are slicing through", "{#lb} passes from {team} have gone straight past a {other} line in the last {#win} minutes."),
            ],
            "es": [
                ("{team} atraviesa a {other}", "{#lb} pases de {team} han superado una línea de {other} en los últimos {#win} minutos."),
            ],
            "ca": [
                ("{team} travessa {other}", "{#lb} passades de {team} han superat una línia de {other} en els últims {#win} minuts."),
            ],
        },
    },
}

# Why it matters right now: the score situation of the team an insight is about. Positive news
# for a team that is behind, or a risk for a team protecting a lead. No numbers.
SITUATION_PHRASES: dict[str, dict[str, str]] = {
    "sit_chasing": {
        "en": "Just what {team} need while they're behind.",
        "es": "Justo lo que necesita {team}, que va por detrás.",
        "ca": "Just el que necessita {team}, que va per darrere.",
    },
    "sit_ahead": {
        "en": "{team} are already ahead, and still pushing.",
        "es": "{team} ya va por delante, y sigue apretando.",
        "ca": "{team} ja va per davant, i continua pressionant.",
    },
    "sit_risk": {
        "en": "Risky for {team} while they're protecting a lead.",
        "es": "Arriesgado para {team} mientras defiende una ventaja.",
        "ca": "Arriscat per a {team} mentre defensa un avantatge.",
    },
    "sit_level_risk": {
        "en": "With the score level, {other} will smell a chance.",
        "es": "Con el empate en el marcador, {other} huele la ocasión.",
        "ca": "Amb l'empat al marcador, {other} ensuma l'ocasió.",
    },
}

# insight kinds that are good news for `team`, and kinds that are a warning sign
GOOD_FOR_TEAM = frozenset(
    {
        "press_surge",
        "midfield_battle",
        "line_breakers",
        "zone_damage",
        "momentum_swing",
        "state_shift",
    }
)
BAD_FOR_TEAM = frozenset({"danger_turnovers", "lines_stretched"})


def situation(kind: str, goals_for: int, goals_against: int) -> str | None:
    """The phrase key for this insight given the score from its team's point of view."""
    if kind in GOOD_FOR_TEAM:
        if goals_for < goals_against:
            return "sit_chasing"
        if goals_for > goals_against:
            return "sit_ahead"
    if kind in BAD_FOR_TEAM:
        if goals_for > goals_against:
            return "sit_risk"
        if goals_for == goals_against:
            return "sit_level_risk"
    return None

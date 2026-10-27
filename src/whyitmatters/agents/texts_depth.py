# ruff: noqa: E501  (sentences read better unbroken)
"""Words for the depth insights: block_drop, hub_player, press_escape, physical_drop.

Same conventions as texts_tactics.py: `{name}` is a word slot, `{#key}` the formatted value of the
claim with that key, and no digit appears in any static text.
"""

from __future__ import annotations

Tpl = dict[str, dict[str, dict[str, tuple[str, str]]]]

DEPTH_TEMPLATES: Tpl = {
    "block_drop": {
        "analyst": {
            "en": (
                "{team} drop deeper",
                "Without the ball, the back line of {team} now stands {#now} from their own goal, down from {#was} over the last {#win} minutes. {other} have more room to play in.",
            ),
            "es": (
                "{team} se hunde",
                "Sin balón, la línea defensiva de {team} está ahora a {#now} de su portería, frente a {#was} antes, en los últimos {#win} minutos. {other} tiene más espacio para jugar.",
            ),
            "ca": (
                "{team} s'enfonsa",
                "Sense pilota, la línia defensiva de {team} és ara a {#now} de la seva porteria, davant {#was} abans, en els últims {#win} minuts. {other} té més espai per jugar.",
            ),
        },
        "fan": {
            "en": (
                "{team} are sitting back",
                "{team} have dropped off: their defence now stands {#now} from goal, where it was {#was}.",
            ),
            "es": (
                "{team} se echa atrás",
                "{team} se ha replegado: su defensa está ahora a {#now} de la portería, antes a {#was}.",
            ),
            "ca": (
                "{team} es fa enrere",
                "{team} s'ha replegat: la seva defensa és ara a {#now} de la porteria, abans a {#was}.",
            ),
        },
    },
    "hub_player": {
        "analyst": {
            "en": (
                "Everything goes through {player}",
                "{player} has made or received {#share} of the completed passes of {team} in the last {#win} minutes, far more than any teammate. The pass network runs through one player.",
            ),
            "es": (
                "Todo pasa por {player}",
                "{player} ha dado o recibido el {#share} de los pases completados de {team} en los últimos {#win} minutos, muy por encima de cualquier compañero. La red de pases pasa por un solo jugador.",
            ),
            "ca": (
                "Tot passa per {player}",
                "{player} ha donat o rebut el {#share} de les passades completades de {team} en els últims {#win} minuts, molt per sobre de qualsevol company. La xarxa de passades passa per un sol jugador.",
            ),
        },
        "fan": {
            "en": (
                "{player} is the hub",
                "{team} keep finding {player}: he is on the end of {#share} of their passes in the last {#win} minutes.",
            ),
            "es": (
                "{player}, el eje del juego",
                "{team} busca una y otra vez a {player}: participa en el {#share} de sus pases en los últimos {#win} minutos.",
            ),
            "ca": (
                "{player}, l'eix del joc",
                "{team} busca una vegada i una altra {player}: participa en el {#share} de les seves passades en els últims {#win} minuts.",
            ),
        },
    },
    "press_escape": {
        "analyst": {
            "en": (
                "{team} are beating the press",
                "{team} have got past the first line of {other} {#esc} times in build-up in the last {#win} minutes, {#rate} of their build-up passes, even though {other} allow only {#ppda} passes per defensive action.",
            ),
            "es": (
                "{team} supera la presión",
                "{team} ha superado la primera línea de {other} {#esc} veces en la salida en los últimos {#win} minutos, el {#rate} de sus pases de salida, aunque {other} solo permite {#ppda} pases por acción defensiva.",
            ),
            "ca": (
                "{team} supera la pressió",
                "{team} ha superat la primera línia de {other} {#esc} vegades en la sortida en els últims {#win} minuts, el {#rate} de les passades de sortida, tot i que {other} només permet {#ppda} passades per acció defensiva.",
            ),
        },
        "fan": {
            "en": (
                "{team} slip the press",
                "{other} are pressing, but {team} keep playing out: {#esc} ways past the first line in the last {#win} minutes.",
            ),
            "es": (
                "{team} se escapa de la presión",
                "{other} aprieta, pero {team} sigue saliendo: {#esc} formas de pasar la primera línea en los últimos {#win} minutos.",
            ),
            "ca": (
                "{team} s'escapa de la pressió",
                "{other} pressiona, però {team} continua sortint: {#esc} maneres de passar la primera línia en els últims {#win} minuts.",
            ),
        },
    },
    "physical_drop": {
        "analyst": {
            "en": (
                "{team} are tiring",
                "The outfield players of {team} are covering {#now} a minute over the last {#win} minutes, down from {#was} earlier in the match. Their legs are going.",
            ),
            "es": (
                "{team} se cansa",
                "Los jugadores de campo de {team} recorren {#now} por minuto en los últimos {#win} minutos, frente a {#was} antes en el partido. Las piernas se resienten.",
            ),
            "ca": (
                "{team} es cansa",
                "Els jugadors de camp de {team} recorren {#now} per minut en els últims {#win} minuts, davant {#was} abans en el partit. Les cames es ressenten.",
            ),
        },
        "fan": {
            "en": (
                "Tired legs at {team}",
                "{team} are slowing down: {#now} a minute per player lately, from {#was} earlier on.",
            ),
            "es": (
                "Piernas cansadas en {team}",
                "{team} baja el ritmo: {#now} por minuto y jugador últimamente, antes {#was}.",
            ),
            "ca": (
                "Cames cansades a {team}",
                "{team} baixa el ritme: {#now} per minut i jugador últimament, abans {#was}.",
            ),
        },
    },
}

DEPTH_ADVICE: dict[str, dict[str, str]] = {
    "block_drop": {
        "en": "{other} could play the ball in behind a back line that stands this deep.",
        "es": "{other} podría jugar el balón a la espalda de una defensa tan retrasada.",
        "ca": "{other} podria jugar la pilota a l'esquena d'una defensa tan endarrerida.",
    },
    "hub_player": {
        "en": "{other} could mark {player} tightly and force the play wide.",
        "es": "{other} podría marcar a {player} de cerca y obligar a jugar por fuera.",
        "ca": "{other} podria marcar {player} de a prop i obligar a jugar per fora.",
    },
    "press_escape": {
        "en": "{other} could press the passes into midfield instead of the first line.",
        "es": "{other} podría presionar los pases al medio del campo en lugar de la primera línea.",
        "ca": "{other} podria pressionar les passades al mig del camp en lloc de la primera línia.",
    },
    "physical_drop": {
        "en": "{team} could use fresh legs: a substitution would restore the tempo.",
        "es": "{team} podría necesitar piernas frescas: un cambio devolvería el ritmo.",
        "ca": "{team} podria necessitar cames fresques: un canvi tornaria el ritme.",
    },
}
DEPTH_ADVICE_FOR: dict[str, str] = {
    "block_drop": "block_drop",
    "hub_player": "hub_player",
    "press_escape": "press_escape",
    "physical_drop": "physical_drop",
}

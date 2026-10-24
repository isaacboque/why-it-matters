"""Words for the tactical insights: cause -> effect templates, driver phrases, coach advice.

Same conventions as generator.py: `{name}` is a word slot, `{#key}` the formatted value of the
claim with that key. Nothing here contains a digit: every number comes from a verified claim.
"""

from __future__ import annotations

Tpl = dict[str, dict[str, dict[str, tuple[str, str]]]]

# {cause} = the ranked drivers joined into one clause (see TemplateGenerator.render)
TEMPLATES: Tpl = {
    "shift_control_why": {
        "analyst": {
            "en": (
                "{team} take control",
                "{team} have taken control: {cause} in the last {#win} minutes. That is "
                "{#poss} of the ball, with {#comp} of their passes completed.",
            ),
            "es": (
                "{team} toma el control",
                "{team} ha tomado el control: {cause} en los últimos {#win} minutos. Eso "
                "es el {#poss} del balón, con el {#comp} de sus pases completados.",
            ),
            "ca": (
                "{team} pren el control",
                "{team} ha près el control: {cause} en els últims {#win} minuts. Això és "
                "el {#poss} de la pilota, amb el {#comp} de les passades completades.",
            ),
        },
        "fan": {
            "en": (
                "{team} are on top",
                "{team} are on top: {cause} in the last {#win} minutes.",
            ),
            "es": (
                "{team} manda",
                "{team} está por encima: {cause} en los últimos {#win} minutos.",
            ),
            "ca": (
                "{team} mana",
                "{team} està per sobre: {cause} en els últims {#win} minuts.",
            ),
        },
    },
    "press_surge": {
        "analyst": {
            "en": (
                "{team} are pressing high",
                "{team} have won the ball back in the opposition half {#hr} times in the last "
                "{#win} minutes and leave {other} just {#ppda} passes per defensive action.",
            ),
            "es": (
                "{team} presiona arriba",
                "{team} ha recuperado el balón en campo de {other} {#hr} veces en los "
                "últimos {#win} minutos y deja a {other} en solo {#ppda} pases por acción "
                "defensiva.",
            ),
            "ca": (
                "{team} pressiona alt",
                "{team} ha recuperat la pilota al camp de {other} {#hr} vegades en els "
                "últims {#win} minuts i deixa {other} en només {#ppda} passades per acció "
                "defensiva.",
            ),
        },
        "fan": {
            "en": (
                "{team} are hunting the ball",
                "{team} keep winning it back high up the pitch: {#hr} times in the last "
                "{#win} minutes. {other} can't settle.",
            ),
            "es": (
                "{team} va a por el balón",
                "{team} recupera el balón arriba una y otra vez: {#hr} veces en los "
                "últimos {#win} minutos. {other} no se asienta.",
            ),
            "ca": (
                "{team} va a per la pilota",
                "{team} recupera la pilota a dalt una vegada i una altra: {#hr} vegades en "
                "els últims {#win} minuts. {other} no s'asseu.",
            ),
        },
    },
    "midfield_battle": {
        "analyst": {
            "en": (
                "{team} are winning the midfield",
                "{team} have won {#share} of the midfield duels ({#n} in the last {#win} "
                "minutes), so {other} can't build through the middle.",
            ),
            "es": (
                "{team} gana el centro del campo",
                "{team} ha ganado el {#share} de los duelos en el medio ({#n} en los "
                "últimos {#win} minutos), así que {other} no puede construir por el centro.",
            ),
            "ca": (
                "{team} guanya el mig del camp",
                "{team} ha guanyat el {#share} dels duels al mig ({#n} en els últims "
                "{#win} minuts), així que {other} no pot construir pel centre.",
            ),
        },
        "fan": {
            "en": (
                "{team} are bossing the middle",
                "{team} are winning most of the battles in midfield: {#share} of them in "
                "the last {#win} minutes.",
            ),
            "es": (
                "{team} manda en el medio",
                "{team} gana la mayoría de las luchas en el centro del campo: el {#share} "
                "en los últimos {#win} minutos.",
            ),
            "ca": (
                "{team} mana al mig",
                "{team} guanya la majoria de les lluites al centre del camp: el {#share} "
                "en els últims {#win} minuts.",
            ),
        },
    },
    "danger_turnovers": {
        "analyst": {
            "en": (
                "{team} are giving it away in dangerous areas",
                "{team} have lost the ball {#n} times in their own half in the last "
                "{#win} minutes. {other} can punish any of them.",
            ),
            "es": (
                "{team} pierde balones en zona peligrosa",
                "{team} ha perdido el balón {#n} veces en su campo en los últimos {#win} "
                "minutos. {other} puede castigar cualquiera de ellas.",
            ),
            "ca": (
                "{team} perd pilotes en zona perillosa",
                "{team} ha perdut la pilota {#n} vegades al seu camp en els últims {#win} "
                "minuts. {other} en pot castigar qualsevol.",
            ),
        },
        "fan": {
            "en": (
                "{team} keep losing it at the back",
                "{team} have given the ball away {#n} times in their own half in the last "
                "{#win} minutes. Dangerous!",
            ),
            "es": (
                "{team} regala el balón atrás",
                "{team} ha perdido el balón {#n} veces en su propio campo en los últimos "
                "{#win} minutos. ¡Peligro!",
            ),
            "ca": (
                "{team} regala la pilota enrere",
                "{team} ha perdut la pilota {#n} vegades al seu propi camp en els últims "
                "{#win} minuts. Perill!",
            ),
        },
    },
    "direct_switch": {
        "analyst": {
            "en": (
                "{team} go long to beat the press",
                "{other} are pressing high ({#ppda} passes per defensive action), so "
                "{team} now play {#lb} of their passes long to bypass it.",
            ),
            "es": (
                "{team} juega largo para saltarse la presión",
                "{other} presiona arriba ({#ppda} pases por acción defensiva), así que "
                "{team} juega ahora el {#lb} de sus pases en largo para evitarla.",
            ),
            "ca": (
                "{team} juga llarg per saltar la pressió",
                "{other} pressiona alt ({#ppda} passades per acció defensiva), així que "
                "{team} juga ara el {#lb} de les seves passades en llarg per evitar-la.",
            ),
        },
        "fan": {
            "en": (
                "{team} are going over the top",
                "{other} are pressing, so {team} are launching it: {#lb} of their passes "
                "are long balls now.",
            ),
            "es": (
                "{team} salta la presión",
                "{other} aprieta, así que {team} la manda larga: el {#lb} de sus pases ya "
                "son balones largos.",
            ),
            "ca": (
                "{team} salta la pressió",
                "{other} pressiona, així que {team} la llança llarga: el {#lb} de les "
                "seves passades ja són pilotes llargues.",
            ),
        },
    },
    "pass_difficulty": {
        "analyst": {
            "en": (
                "{player}: hardest pass of the match",
                "{player} completes a pass with a difficulty rating of {#pd}, the hardest "
                "completed so far.",
            ),
            "es": (
                "{player}: el pase más difícil",
                "{player} completa un pase con una dificultad de {#pd}, el más complicado "
                "hasta ahora.",
            ),
            "ca": (
                "{player}: la passada més difícil",
                "{player} completa una passada amb una dificultat de {#pd}, la més "
                "complicada fins ara.",
            ),
        },
        "fan": {
            "en": ("What a pass!", "{player} just played the hardest pass of the match so far."),
            "es": ("¡Qué pase!", "{player} acaba de dar el pase más difícil del partido."),
            "ca": ("Quina passada!", "{player} acaba de fer la passada més difícil del partit."),
        },
    },
    "shot_speed": {
        "analyst": {
            "en": (
                "{player}: fastest shot of the match",
                "{player} strikes it at {#kmh} km/h, the hardest shot so far.",
            ),
            "es": (
                "{player}: el disparo más potente",
                "{player} remata a {#kmh} km/h, el disparo más fuerte hasta ahora.",
            ),
            "ca": (
                "{player}: el xut més potent",
                "{player} xuta a {#kmh} km/h, el xut més fort fins ara.",
            ),
        },
        "fan": {
            "en": ("Thunderbolt!", "{player} just hit the fastest shot of the match: {#kmh} km/h."),
            "es": ("¡Un cañonazo!", "{player} acaba de soltar el disparo más rápido: {#kmh} km/h."),
            "ca": ("Una canonada!", "{player} acaba de fer el xut més ràpid: {#kmh} km/h."),
        },
    },
}

# One clause per driver; {#v} becomes the driver's own claim key (dv1, dv2, ...).
DRIVER_PHRASES: dict[str, dict[str, str]] = {
    "duel_mid": {
        "en": "winning {#v} of the midfield duels",
        "es": "ganando el {#v} de los duelos en el medio del campo",
        "ca": "guanyant el {#v} dels duels al mig del camp",
    },
    "duel_att": {
        "en": "winning {#v} of the duels near the opposition box",
        "es": "ganando el {#v} de los duelos cerca del área de {other}",
        "ca": "guanyant el {#v} dels duels a prop de l'àrea de {other}",
    },
    "pressures": {
        "en": "closing {other} down {#v} times",
        "es": "presionando a {other} {#v} veces",
        "ca": "pressionant {other} {#v} vegades",
    },
    "high_rec": {
        "en": "winning the ball back in the opposition half {#v} times",
        "es": "recuperando el balón en campo de {other} {#v} veces",
        "ca": "recuperant la pilota al camp de {other} {#v} vegades",
    },
    "final_rec": {
        "en": "recovering the ball {#v} times in the final third",
        "es": "recuperando el balón {#v} veces en el último tercio",
        "ca": "recuperant la pilota {#v} vegades al darrer terç",
    },
    "counter_press": {
        "en": "winning it straight back {#v} times after losing it",
        "es": "recuperando el balón al instante {#v} veces tras perderlo",
        "ca": "recuperant la pilota a l'instant {#v} vegades després de perdre-la",
    },
    "ppda": {
        "en": "leaving {other} just {#v} passes per defensive action",
        "es": "dejando a {other} en solo {#v} pases por acción defensiva",
        "ca": "deixant {other} en només {#v} passades per acció defensiva",
    },
    "opp_losses": {
        "en": "forcing {other} into {#v} losses in their own half",
        "es": "obligando a {other} a perder el balón {#v} veces en su campo",
        "ca": "obligant {other} a perdre la pilota {#v} vegades al seu camp",
    },
    "progressive": {
        "en": "playing {#v} progressive passes",
        "es": "dando {#v} pases progresivos",
        "ca": "fent {#v} passades progressives",
    },
    "long_ball": {
        "en": "going long with {#v} of their passes",
        "es": "jugando largo en el {#v} de sus pases",
        "ca": "jugant llarg en el {#v} de les seves passades",
    },
}

JOINERS: dict[str, tuple[str, str]] = {  # (separator, last separator)
    "en": (", ", " and "),
    "es": (", ", " y "),
    "ca": (", ", " i "),
}

# How the goal / big chance came about (slot "buildup"); numbers come from claims sec / lb
BUILDUP_PHRASES: dict[str, dict[str, str]] = {
    "buildup_counter": {
        "en": "{team} won it straight back and the move took {#sec} seconds.",
        "es": "{team} la recuperó al instante y la jugada duró {#sec} segundos.",
        "ca": "{team} la va recuperar a l'instant i la jugada va durar {#sec} segons.",
    },
    "buildup_high": {
        "en": "It came {#sec} seconds after {team} won the ball high up the pitch.",
        "es": "Llegó {#sec} segundos después de que {team} recuperase el balón arriba.",
        "ca": "Va arribar {#sec} segons després que {team} recuperés la pilota a dalt.",
    },
    "buildup_long": {
        "en": "A long ball over the press set it up.",
        "es": "Un pase largo por encima de la presión lo preparó.",
        "ca": "Una passada llarga per sobre de la pressió ho va preparar.",
    },
}

# Coach mode: one rule-based sentence on what the other side could change. No numbers.
ADVICE: dict[str, dict[str, str]] = {
    "press": {
        "en": "{other} could go long to bypass the press.",
        "es": "{other} podría jugar largo para saltarse la presión.",
        "ca": "{other} podria jugar llarg per saltar-se la pressió.",
    },
    "duel_mid": {
        "en": "{other} could add a body in midfield to win the second balls.",
        "es": "{other} podría meter un jugador más en el medio para ganar los rechaces.",
        "ca": "{other} podria posar un jugador més al mig per guanyar les segones jugades.",
    },
    "duel_att": {
        "en": "{other} could clear earlier instead of playing out under pressure.",
        "es": "{other} podría despejar antes en lugar de sacar jugando bajo presión.",
        "ca": "{other} podria refusar abans en lloc de sortir jugant sota pressió.",
    },
    "progressive": {
        "en": "{other} could drop a line deeper to cut the passing lanes.",
        "es": "{other} podría bajar una línea para cortar las líneas de pase.",
        "ca": "{other} podria baixar una línia per tallar les línies de passada.",
    },
    "long_ball": {
        "en": "{other} could drop deeper and let the long balls come to them.",
        "es": "{other} podría retrasarse y dejar que los balones largos vengan a ellos.",
        "ca": "{other} podria retrassar-se i deixar que les pilotes llargues vinguin a ells.",
    },
    "danger_turnovers": {
        "en": "{team} could play long instead of building from the back.",
        "es": "{team} podría jugar largo en lugar de construir desde atrás.",
        "ca": "{team} podria jugar llarg en lloc de construir des del darrere.",
    },
}

# driver / insight kind -> ADVICE key
ADVICE_FOR: dict[str, str] = {
    "duel_mid": "duel_mid",
    "duel_att": "duel_att",
    "pressures": "press",
    "high_rec": "press",
    "final_rec": "press",
    "counter_press": "press",
    "ppda": "press",
    "opp_losses": "press",
    "progressive": "progressive",
    "long_ball": "long_ball",
    "press_surge": "press",
    "midfield_battle": "duel_mid",
    "danger_turnovers": "danger_turnovers",
    "direct_switch": "long_ball",
}

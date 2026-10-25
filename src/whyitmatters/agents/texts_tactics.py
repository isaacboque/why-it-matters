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


# Damage and shape (freeze frames + Expected Threat). {lane} is a LANE_PHRASES key.
DAMAGE_TEMPLATES: Tpl = {
    "line_breakers": {
        "analyst": {
            "en": (
                "{team} are playing through the lines",
                "{team} have played {#lb} passes past at least one {other} line in the last "
                "{#win} minutes, and found a player between their lines {#bl} times.",
            ),
            "es": (
                "{team} juega entre líneas",
                "{team} ha dado {#lb} pases que superan al menos una línea de {other} en los "
                "últimos {#win} minutos, y ha encontrado a un jugador entre sus líneas "
                "{#bl} veces.",
            ),
            "ca": (
                "{team} juga entre línies",
                "{team} ha fet {#lb} passades que superen almenys una línia de {other} en els "
                "últims {#win} minuts, i ha trobat un jugador entre les seves línies "
                "{#bl} vegades.",
            ),
        },
        "fan": {
            "en": (
                "{team} are cutting through",
                "{team} keep finding passes through {other}: {#lb} of them in the last "
                "{#win} minutes.",
            ),
            "es": (
                "{team} está rompiendo líneas",
                "{team} encuentra pases a través de {other} una y otra vez: {#lb} en los "
                "últimos {#win} minutos.",
            ),
            "ca": (
                "{team} està trencant línies",
                "{team} troba passades a través de {other} una vegada i una altra: {#lb} en "
                "els últims {#win} minuts.",
            ),
        },
    },
    "zone_damage": {
        "analyst": {
            "en": (
                "{team} are hurting {other} {lane}",
                "{#share} of the threat {team} have created in the last {#win} minutes came "
                "{lane}: {#xt} expected threat in all.",
            ),
            "es": (
                "{team} hace daño {lane}",
                "El {#share} de la amenaza que ha generado {team} en los últimos {#win} "
                "minutos llegó {lane}: {#xt} de amenaza esperada en total.",
            ),
            "ca": (
                "{team} fa mal {lane}",
                "El {#share} de l'amenaça que ha generat {team} en els últims {#win} minuts "
                "ha arribat {lane}: {#xt} d'amenaça esperada en total.",
            ),
        },
        "fan": {
            "en": (
                "Danger {lane}",
                "{team} are getting joy {lane}: {#share} of their dangerous moves in the last "
                "{#win} minutes went that way.",
            ),
            "es": (
                "Peligro {lane}",
                "{team} encuentra el camino {lane}: el {#share} de sus jugadas peligrosas en "
                "los últimos {#win} minutos fue por ahí.",
            ),
            "ca": (
                "Perill {lane}",
                "{team} troba el camí {lane}: el {#share} de les jugades perilloses dels "
                "últims {#win} minuts ha anat per allà.",
            ),
        },
    },
    "momentum_swing": {
        "analyst": {
            "en": (
                "Momentum swings to {team}",
                "{team} are now the more dangerous side: {#xt} expected threat in the last "
                "{#win} minutes against {#xt_o} for {other}, who had been on top.",
            ),
            "es": (
                "El impulso cambia hacia {team}",
                "{team} es ahora el equipo más peligroso: {#xt} de amenaza esperada en los "
                "últimos {#win} minutos frente a {#xt_o} de {other}, que llevaba la "
                "iniciativa.",
            ),
            "ca": (
                "L'impuls canvia cap a {team}",
                "{team} és ara l'equip més perillós: {#xt} d'amenaça esperada en els últims "
                "{#win} minuts davant {#xt_o} de {other}, que portava la iniciativa.",
            ),
        },
        "fan": {
            "en": (
                "{team} have the momentum",
                "The tide has turned: {team} are the ones carrying the threat now, "
                "{#xt} to {#xt_o} in the last {#win} minutes.",
            ),
            "es": (
                "{team} tiene el impulso",
                "Ha cambiado la marea: ahora el peligro lo lleva {team}, {#xt} a {#xt_o} en "
                "los últimos {#win} minutos.",
            ),
            "ca": (
                "{team} té l'impuls",
                "Ha canviat la marea: ara el perill el porta {team}, {#xt} a {#xt_o} en els "
                "últims {#win} minuts.",
            ),
        },
    },
    "shape_change": {
        "analyst": {
            "en": (
                "{team} change shape",
                "With the ball, {team} have moved from a {#was} to a {#now} over the last "
                "{#win} minutes.",
            ),
            "es": (
                "{team} cambia el dibujo",
                "Con balón, {team} ha pasado de un {#was} a un {#now} en los últimos {#win} "
                "minutos.",
            ),
            "ca": (
                "{team} canvia el dibuix",
                "Amb pilota, {team} ha passat d'un {#was} a un {#now} en els últims {#win} minuts.",
            ),
        },
        "fan": {
            "en": (
                "{team} have switched it up",
                "New shape for {team} on the ball: a {#now} now, after a {#was}.",
            ),
            "es": (
                "{team} cambia el sistema",
                "Nuevo dibujo de {team} con balón: ahora un {#now}, antes un {#was}.",
            ),
            "ca": (
                "{team} canvia el sistema",
                "Nou dibuix de {team} amb pilota: ara un {#now}, abans un {#was}.",
            ),
        },
    },
    "lines_stretched": {
        "analyst": {
            "en": (
                "{team} are stretched",
                "Without the ball, {team} now leave {#now} between their back line and "
                "midfield, up from {#was}. That is space for {other} to receive in.",
            ),
            "es": (
                "{team} está estirado",
                "Sin balón, {team} deja ahora {#now} entre su defensa y el centro del campo, "
                "frente a {#was} antes. Es espacio para que {other} reciba.",
            ),
            "ca": (
                "{team} està estirat",
                "Sense pilota, {team} deixa ara {#now} entre la defensa i el mig del camp, "
                "davant {#was} abans. És espai perquè {other} rebi.",
            ),
        },
        "fan": {
            "en": (
                "Gaps are opening for {other}",
                "{team}'s lines have pulled apart: {#now} between defence and midfield, "
                "from {#was}.",
            ),
            "es": (
                "Se abren huecos para {other}",
                "Las líneas de {team} se han separado: {#now} entre defensa y medio, antes {#was}.",
            ),
            "ca": (
                "S'obren forats per a {other}",
                "Les línies de {team} s'han separat: {#now} entre defensa i mig, abans {#was}.",
            ),
        },
    },
    "most_dangerous_pass": {
        "analyst": {
            "en": (
                "{player} breaks it open",
                "{player}'s pass took {#pk} {other} players out of the game and added "
                "{#xt} expected threat.",
            ),
            "es": (
                "{player} rompe el partido",
                "El pase de {player} dejó fuera a {#pk} jugadores de {other} y sumó {#xt} de "
                "amenaza esperada.",
            ),
            "ca": (
                "{player} trenca el partit",
                "La passada de {player} va deixar fora {#pk} jugadors de {other} i va sumar "
                "{#xt} d'amenaça esperada.",
            ),
        },
        "fan": {
            "en": (
                "What a ball from {player}!",
                "One pass, {#pk} {other} players taken out. That's how you open a defence.",
            ),
            "es": (
                "¡Qué pase de {player}!",
                "Un pase y {#pk} jugadores de {other} fuera de la jugada. Así se abre una defensa.",
            ),
            "ca": (
                "Quina passada de {player}!",
                "Una passada i {#pk} jugadors de {other} fora de la jugada. Així s'obre una "
                "defensa.",
            ),
        },
    },
}
TEMPLATES.update(DAMAGE_TEMPLATES)

# Where the threat came from (slot "lane"), from the attacking team's point of view
LANE_PHRASES: dict[str, dict[str, str]] = {
    "lane_left": {"en": "down the left", "es": "por la izquierda", "ca": "per l'esquerra"},
    "lane_centre": {"en": "through the middle", "es": "por el centro", "ca": "pel centre"},
    "lane_right": {"en": "down the right", "es": "por la derecha", "ca": "per la dreta"},
}

DAMAGE_ADVICE: dict[str, dict[str, str]] = {
    "line_breakers": {
        "en": "{other} could step a midfielder in to screen the passing lane into the gap.",
        "es": "{other} podría adelantar a un mediocentro para tapar la línea de pase al hueco.",
        "ca": "{other} podria avançar un migcampista per tapar la línia de passada al forat.",
    },
    "zone_damage": {
        "en": "{other} could shift the block and double up {lane}.",
        "es": "{other} podría bascular el bloque y doblar la marca {lane}.",
        "ca": "{other} podria bascular el bloc i doblar la marca {lane}.",
    },
    "momentum": {
        "en": "{other} could slow the game down and keep the ball for a spell.",
        "es": "{other} podría pausar el partido y tener el balón un rato.",
        "ca": "{other} podria pausar el partit i tenir la pilota una estona.",
    },
    "shape_change": {
        "en": "{other} could match the new shape so nobody is left free between the lines.",
        "es": "{other} podría igualar el nuevo dibujo para no dejar a nadie libre entre líneas.",
        "ca": "{other} podria igualar el nou dibuix per no deixar ningú lliure entre línies.",
    },
    "stretched": {
        "en": "{team} could push the back line up or drop a midfielder to close the gap.",
        "es": "{team} podría subir la defensa o bajar a un mediocentro para cerrar el hueco.",
        "ca": "{team} podria pujar la defensa o baixar un migcampista per tancar el forat.",
    },
}
ADVICE.update(DAMAGE_ADVICE)
ADVICE_FOR.update(
    {
        "line_breakers": "line_breakers",
        "zone_damage": "zone_damage",
        "momentum_swing": "momentum",
        "shape_change": "shape_change",
        "lines_stretched": "stretched",
        "most_dangerous_pass": "line_breakers",
    }
)

"""Text generation behind a pluggable interface.

`TemplateGenerator` is the offline default: deterministic, instant, multilingual. A hosted
model (e.g. on Microsoft Foundry) implements the same `TextGenerator` protocol. Either way
numbers are never typed by the generator: they come only from verified claims, formatted
here, and the Verifier rejects any number in the text that no claim supports.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Protocol

from whyitmatters.agents.models import Claim, Lang, Mode
from whyitmatters.agents.texts_tactics import (
    ADVICE,
    BUILDUP_PHRASES,
    DRIVER_PHRASES,
    JOINERS,
    LANE_PHRASES,
    TEMPLATES,
)
from whyitmatters.agents.texts_variants import SITUATION_PHRASES, VARIANTS

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

TEMPLATE_LANGS = ("en", "es", "ca")  # languages the offline templates are written in
# Decimal separator by base language; anything not listed uses "."
DECIMAL_SEP = {
    **dict.fromkeys(
        ("es", "ca", "fr", "de", "it", "pt", "nl", "pl", "ru", "tr", "sv", "da", "nb", "fi", "cs"),
        ",",
    ),
}


def base_lang(lang: Lang) -> str:
    """'pt-BR' -> 'pt'."""
    return lang.split("-")[0].split("_")[0].lower()


def template_lang(lang: Lang) -> str:
    """The language the offline templates will actually be written in (English if none)."""
    base = base_lang(lang)
    return base if base in TEMPLATE_LANGS else "en"


def fmt(claim: Claim, lang: Lang) -> str:
    """How a claim's value appears on screen in a given language."""
    v = claim.value
    if claim.unit == "share":
        return f"{round(v * 100)}%"
    if claim.unit == "formation":
        return "-".join(str(int(round(v))))  # 442.0 -> "4-4-2"
    if claim.unit == "metres":
        return f"{round(v)} m"
    if claim.unit == "m2":
        return f"{round(v)} m²"
    if claim.unit == "xt":
        s = f"{v:.2f}"
        return s.replace(".", DECIMAL_SEP.get(base_lang(lang), "."))
    if claim.unit in ("xg", "index"):
        s = f"{v:.2f}"
    elif claim.unit == "rate":
        s = f"{v:.1f}"
    else:  # count, kmh, minutes, seconds
        s = f"{round(v)}"
    return s.replace(".", DECIMAL_SEP.get(base_lang(lang), "."))


def numbers_in(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


class Rendered(NamedTuple):
    """What a generator wrote, and who wrote it."""

    headline: str
    body: str
    source: str = "template"  # "model" | "template" | "template_fallback" | "other"
    translation_unavailable: bool = False  # English text standing in for the requested language


class TextGenerator(Protocol):
    name: str

    def render(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> tuple[str, str]:
        """Return (headline, body)."""
        ...


def render_with_source(
    generator: TextGenerator,
    template: str,
    mode: Mode,
    lang: Lang,
    slots: dict[str, str],
    claims: list[Claim],
) -> Rendered:
    """Render through any generator; those that know who wrote the text (`render_full`) say so."""
    full = getattr(generator, "render_full", None)
    if full is not None:
        return full(template, mode, lang, slots, claims)
    headline, body = generator.render(template, mode, lang, slots, claims)
    return Rendered(headline, body, "other")


# ---------------------------------------------------------------------------- templates
# key: template id -> mode ("analyst" | "fan") -> lang -> (headline, body)
# {name} = a word slot; {#key} = the formatted value of the claim with that key.
T: dict[str, dict[str, dict[str, tuple[str, str]]]] = {
    "shift_control": {
        "analyst": {
            "en": (
                "{team} take control",
                "{team} have had {#poss} of the ball over the last {#win} minutes and "
                "complete {#comp} of their passes. {other} can't get out.",
            ),
            "es": (
                "{team} toma el control",
                "{team} ha tenido el {#poss} del balón en los últimos {#win} minutos y "
                "completa el {#comp} de sus pases. {other} no consigue salir.",
            ),
            "ca": (
                "{team} pren el control",
                "{team} ha tingut el {#poss} de la pilota en els últims {#win} minuts i "
                "completa el {#comp} de les passades. {other} no aconsegueix sortir.",
            ),
        },
        "fan": {
            "en": (
                "{team} are on top",
                "{team} have taken over: they've had the ball {#poss} of the time "
                "in the last {#win} minutes.",
            ),
            "es": (
                "{team} manda",
                "{team} se ha hecho con el partido: ha tenido el balón el {#poss} "
                "del tiempo en los últimos {#win} minutos.",
            ),
            "ca": (
                "{team} mana",
                "{team} s'ha fet amb el partit: ha tingut la pilota el {#poss} "
                "del temps en els últims {#win} minuts.",
            ),
        },
    },
    "shift_chaos": {
        "analyst": {
            "en": (
                "The game has broken open",
                "{#turn} turnovers a minute over the last {#win} minutes: neither side can "
                "keep the ball. Expect chances at both ends.",
            ),
            "es": (
                "El partido se ha roto",
                "{#turn} pérdidas por minuto en los últimos {#win} minutos: nadie retiene "
                "el balón. Habrá ocasiones en las dos áreas.",
            ),
            "ca": (
                "El partit s'ha trencat",
                "{#turn} pèrdues per minut en els últims {#win} minuts: ningú reté la "
                "pilota. Hi haurà ocasions a les dues àrees.",
            ),
        },
        "fan": {
            "en": (
                "End to end now!",
                "Nobody can keep the ball: it's changing hands {#turn} times a minute. "
                "Anything can happen.",
            ),
            "es": (
                "¡Ahora es un ida y vuelta!",
                "Nadie se queda el balón: cambia de manos {#turn} veces por minuto. "
                "Puede pasar cualquier cosa.",
            ),
            "ca": (
                "Ara és un anar i tornar!",
                "Ningú es queda la pilota: canvia de mans {#turn} vegades per minut. "
                "Pot passar qualsevol cosa.",
            ),
        },
    },
    "shift_balanced": {
        "analyst": {
            "en": (
                "Control is up for grabs",
                "Neither side is in control any more. Possession over the last {#win} "
                "minutes: {home} {#poss_h}, {away} {#poss_a}. No clear edge in passing "
                "either.",
            ),
            "es": (
                "El control está en el aire",
                "Ya nadie manda. Posesión en los últimos {#win} minutos: {home} {#poss_h}, "
                "{away} {#poss_a}. Sin ventaja clara en el pase.",
            ),
            "ca": (
                "El control és a l'aire",
                "Ja no mana ningú. Possessió en els últims {#win} minuts: {home} {#poss_h}, "
                "{away} {#poss_a}. Sense avantatge clar en la passada.",
            ),
        },
        "fan": {
            "en": (
                "Nobody's in charge now",
                "The game has settled. Ball over the last {#win} minutes: {home} "
                "{#poss_h}, {away} {#poss_a}. Neither team on top.",
            ),
            "es": (
                "Ahora no manda nadie",
                "El partido se ha calmado. Balón en los últimos {#win} minutos: {home} "
                "{#poss_h}, {away} {#poss_a}. Nadie por encima.",
            ),
            "ca": (
                "Ara no mana ningú",
                "El partit s'ha calmat. Pilota en els últims {#win} minuts: {home} "
                "{#poss_h}, {away} {#poss_a}. Ningú per sobre.",
            ),
        },
    },
    "goal": {
        "analyst": {
            "en": (
                "GOAL {home} {#sh}–{#sa} {away}",
                "{player} scores from a chance worth {#xg} xG. {flow} {buildup}",
            ),
            "es": (
                "GOL {home} {#sh}–{#sa} {away}",
                "{player} marca en una ocasión de {#xg} xG. {flow} {buildup}",
            ),
            "ca": (
                "GOL {home} {#sh}–{#sa} {away}",
                "{player} marca en una ocasió de {#xg} xG. {flow} {buildup}",
            ),
        },
        "fan": {
            "en": (
                "GOAL! {player}!",
                "{team} score! It's {home} {#sh}–{#sa} {away}. {flow} {buildup}",
            ),
            "es": (
                "¡GOL! ¡{player}!",
                "¡Marca {team}! {home} {#sh}–{#sa} {away}. {flow} {buildup}",
            ),
            "ca": ("GOL! {player}!", "Marca {team}! {home} {#sh}–{#sa} {away}. {flow} {buildup}"),
        },
    },
    "big_chance": {
        "analyst": {
            "en": (
                "Big chance for {team}",
                "{player} misses a {#xg} xG chance: shots like that go in {#xgpct} of the time.",
            ),
            "es": (
                "Ocasión clara de {team}",
                "{player} falla una ocasión de {#xg} xG: tiros así acaban en gol el "
                "{#xgpct} de las veces.",
            ),
            "ca": (
                "Ocasió clara de {team}",
                "{player} falla una ocasió de {#xg} xG: xuts així acaben en gol el "
                "{#xgpct} de les vegades.",
            ),
        },
        "fan": {
            "en": (
                "So close!",
                "{player} should have scored: chances like that go in {#xgpct} of the time.",
            ),
            "es": (
                "¡Uy, casi!",
                "{player} tenía que marcar: ocasiones así entran el {#xgpct} de las veces.",
            ),
            "ca": (
                "Uf, per poc!",
                "{player} havia de marcar: ocasions així entren el {#xgpct} de les vegades.",
            ),
        },
    },
    "top_speed": {
        "analyst": {
            "en": (
                "{player}: fastest run of the match",
                "{player} carries the ball at {#kmh} km/h, the top speed recorded so far.",
            ),
            "es": (
                "{player}: la conducción más rápida",
                "{player} conduce a {#kmh} km/h, la velocidad máxima del partido.",
            ),
            "ca": (
                "{player}: la conducció més ràpida",
                "{player} condueix a {#kmh} km/h, la velocitat màxima del partit.",
            ),
        },
        "fan": {
            "en": ("Rapid!", "{player} just flew past at {#kmh} km/h, the fastest of the match."),
            "es": (
                "¡Un cohete!",
                "{player} acaba de volar a {#kmh} km/h, lo más rápido del partido.",
            ),
            "ca": ("Un coet!", "{player} acaba de volar a {#kmh} km/h, el més ràpid del partit."),
        },
    },
    "pass_master": {
        "analyst": {
            "en": ("{player} is running the game", "{player} has completed {#n} passes so far."),
            "es": ("{player} dirige el juego", "{player} ya ha completado {#n} pases."),
            "ca": ("{player} dirigeix el joc", "{player} ja ha completat {#n} passades."),
        },
        "fan": {
            "en": ("{player} is everywhere", "{player} has completed {#n} passes already."),
            "es": ("{player} está en todas", "{player} ya lleva {#n} pases completados."),
            "ca": ("{player} és a tot arreu", "{player} ja porta {#n} passades completades."),
        },
    },
    "recap": {
        "analyst": {
            "en": (
                "Full time: {home} {#sh}–{#sa} {away}",
                "Possession: {home} {#poss_h}, {away} {#poss_a}. Expected goals: {home} "
                "{#xg_h}, {away} {#xg_a}. {verdict}",
            ),
            "es": (
                "Final: {home} {#sh}–{#sa} {away}",
                "Posesión: {home} {#poss_h}, {away} {#poss_a}. Goles esperados: {home} "
                "{#xg_h}, {away} {#xg_a}. {verdict}",
            ),
            "ca": (
                "Final: {home} {#sh}–{#sa} {away}",
                "Possessió: {home} {#poss_h}, {away} {#poss_a}. Gols esperats: {home} "
                "{#xg_h}, {away} {#xg_a}. {verdict}",
            ),
        },
        "fan": {
            "en": ("Full time: {home} {#sh}–{#sa} {away}", "{verdict}"),
            "es": ("Final: {home} {#sh}–{#sa} {away}", "{verdict}"),
            "ca": ("Final: {home} {#sh}–{#sa} {away}", "{verdict}"),
        },
    },
}

T.update(TEMPLATES)

# Number-free phrases chosen by the agents (keys go in slots as "flow" / "verdict").
PHRASES: dict[str, dict[str, str]] = {
    "flow_against": {
        "en": "Against the run of play: {other} were in control.",
        "es": "Contra corriente: dominaba {other}.",
        "ca": "Contra corrent: dominava {other}.",
    },
    "flow_with": {
        "en": "It had been coming: {team} were in control.",
        "es": "Se veía venir: dominaba {team}.",
        "ca": "Es veia venir: dominava {team}.",
    },
    "flow_chaos": {
        "en": "The broken game finally produced a goal.",
        "es": "El partido roto acabó dando un gol.",
        "ca": "El partit trencat ha acabat donant un gol.",
    },
    "flow_none": {"en": "", "es": "", "ca": ""},
    **BUILDUP_PHRASES,
    **LANE_PHRASES,
    **SITUATION_PHRASES,
    "verdict_deserved": {
        "en": "A deserved win for {winner}.",
        "es": "Victoria merecida de {winner}.",
        "ca": "Victòria merescuda de {winner}.",
    },
    "verdict_robbery": {
        "en": "{winner} take the points, but {loser} created more.",
        "es": "{winner} se lleva los puntos, pero {loser} generó más.",
        "ca": "{winner} s'emporta els punts, però {loser} va generar més.",
    },
    "verdict_draw": {
        "en": "Honours even.",
        "es": "Reparto de puntos.",
        "ca": "Repartiment de punts.",
    },
}

_SLOT_RE = re.compile(r"\{(#?)(\w+)\}")


def _cause(spec: str, lang: Lang) -> str:
    """'duel_mid:dv1,high_rec:dv2' -> one clause: the driver phrases, each bound to its claim."""
    parts = []
    for item in filter(None, spec.split(",")):
        driver, claim_key = item.split(":")
        parts.append(DRIVER_PHRASES[driver][lang].replace("{#v}", f"{{#{claim_key}}}"))
    if len(parts) < 2:
        return "".join(parts)
    sep, last = JOINERS[lang]
    return sep.join(parts[:-1]) + last + parts[-1]


def pick_wording(template: str, style: str, lang: str, variant: str) -> tuple[str, str]:
    """The base wording or one of its alternatives (texts_variants.py), rotating by `variant`."""
    alts = VARIANTS.get(template, {}).get(style, {}).get(lang, [])
    k = int(variant) % (1 + len(alts)) if variant.isdigit() else 0
    return T[template][style][lang] if k == 0 else alts[k - 1]


class TemplateGenerator:
    name = "template"

    def render(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> tuple[str, str]:
        out = self.render_full(template, mode, lang, slots, claims)
        return out.headline, out.body

    def render_full(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> Rendered:
        """Written in `lang` when a template exists for it, otherwise in English (flagged)."""
        base = base_lang(lang)
        lang = template_lang(lang)
        headline, body = self._fill(template, mode, lang, slots, claims)
        return Rendered(headline, body, "template", base not in TEMPLATE_LANGS)

    def _fill(
        self, template: str, mode: Mode, lang: str, slots: dict[str, str], claims: list[Claim]
    ) -> tuple[str, str]:
        style = "analyst" if mode in ("analyst", "coach") else "fan"
        headline_t, body_t = pick_wording(template, style, lang, slots.get("variant", "0"))
        if slots.get("situation") in PHRASES:
            body_t = f"{body_t} {{situation}}"
        if mode == "coach" and slots.get("advice") in ADVICE:
            body_t = f"{body_t} {ADVICE[slots['advice']][lang]}"
        values = {c.key: fmt(c, lang) for c in claims}
        words = dict(slots)
        for slot in ("flow", "verdict", "buildup", "lane", "situation"):
            phrase_key = words.get(slot)
            if phrase_key in PHRASES:
                words[slot] = PHRASES[phrase_key][lang]
        words["cause"] = _cause(slots.get("cause", ""), lang)

        def fill(text: str, depth: int = 0) -> str:
            def sub(m: re.Match[str]) -> str:
                is_num, key = m.group(1) == "#", m.group(2)
                if is_num:
                    return values.get(key, f"{{#{key}}}")
                return words.get(key, "")

            out = _SLOT_RE.sub(sub, text)
            # phrases may themselves contain word slots ({other}, {winner})
            return fill(out, depth + 1) if depth < 2 and _SLOT_RE.search(out) else out

        return fill(headline_t).strip(), " ".join(fill(body_t).split())

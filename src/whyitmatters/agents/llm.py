"""Model-written captions in any language, behind the same `TextGenerator` interface.

The model never sees the match. It receives a small JSON brief: the insight kind, the mode, the
target language (any BCP-47 code), the team and player names, and the verified claims already
formatted for that language (plus the English template draft, so it knows what each number
means). It must answer `{"headline", "body"}`, and nothing it writes airs until it passes:

1. numbers: every number must match a claim, formatted for the language (locale-aware decimal
   separator), the same check the Verifier applies to template text;
2. names: no known team or player outside the brief may appear;
3. length: a caption has to fit a lower third.

A failed answer is retried (up to `max_retries`) with the reasons in the prompt; after that the
offline template takes over (English plus a "translation unavailable" flag for languages the
templates do not cover). The text that finally aired is recorded as written by `model` or
`template_fallback`. Answers are cached per (insight, mode, language) and a per-match call
budget (`max_calls`, default 60) caps cost.

Providers (official `openai` package, imported lazily; install with `pip install ".[llm]"`):
Azure OpenAI / Microsoft Foundry, or GitHub Models as a free fallback. See docs/LLM.md.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from whyitmatters.agents.generator import (
    Rendered,
    TemplateGenerator,
    TextGenerator,
    fmt,
)
from whyitmatters.agents.guardrails import (
    MAX_BODY_CHARS,
    MAX_HEADLINE_CHARS,
    NAME_SLOTS,
    brief_names,
    known_names,
    length_problem,
    name_violations,
)
from whyitmatters.agents.models import Claim, Lang, Mode
from whyitmatters.agents.verifier import Verifier
from whyitmatters.schema import MatchMeta

log = logging.getLogger(__name__)

DEFAULT_MAX_CALLS = 60
DEFAULT_RETRIES = 2
DEFAULT_TIMEOUT_S = 20.0
GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"
GITHUB_MODELS_DEFAULT_MODEL = "openai/gpt-4o-mini"
AZURE_API_VERSION = "2024-10-21"

SYSTEM_PROMPT = (
    "You write one short caption for a football TV graphic. You get a JSON brief. "
    "Write in the language given by `language` (a BCP-47 code). Style by `mode`: analyst = "
    "precise and tactical; fan = plain and lively; player_focus = about the player; coach = the "
    "analyst facts, then ONE sentence on what the other side could change. "
    "Use ONLY the numbers in `claims[].text`, copied exactly as written (ASCII digits, same "
    "decimal separator), and ONLY the team and player names in `names`. Never add any other "
    "number, statistic, team or player, and never write a digit that is not in `claims`. "
    "`draft_en` is a reference that shows what the claims mean; do not copy it if the language "
    "is not English. Respect `limits`. Reply with JSON only: "
    '{"headline": "...", "body": "..."}.'
)

METRIC_WORDS = {
    "possession_share": "share of the ball",
    "pass_completion": "pass completion",
    "field_tilt": "share of final-third passes",
    "turnovers_per_min": "turnovers per minute (both teams)",
    "window_minutes": "length of the window in minutes",
    "shot_xg": "expected goals of the shot",
    "score_home": "home goals after the event",
    "score_away": "away goals after the event",
    "player_completed_passes": "completed passes by the player so far",
    "carry_speed_kmh": "speed of the carry in km/h",
    "team_xg": "team expected goals",
    "duel_share_def": "share of duels won in the team's own third",
    "duel_share_mid": "share of midfield duels won",
    "duel_share_att": "share of duels won in the final third",
    "duels_won_mid": "midfield duels won",
    "high_recoveries": "times the ball was won back in the opposition half",
    "final_third_recoveries": "times the ball was won back in the final third",
    "counter_press": "times the ball was won straight back after losing it",
    "own_half_losses": "times the ball was lost in the team's own half",
    "progressive_passes": "progressive passes",
    "long_ball_share": "share of passes that are long balls",
    "central_buildup_share": "share of build-up passes through the middle",
    "ppda": "opposition passes per defensive action (lower = harder press)",
    "pressures": "pressures applied",
    "pass_difficulty": "difficulty rating of the pass",
    "shot_speed_kmh": "speed of the shot in km/h",
    "buildup_seconds": "seconds from winning the ball to the shot",
    "counter_press_in_move": "1 if the move began with a counter-press",
    "long_balls_in_move": "long balls in the move",
    "xt": "expected threat (xT) the team added with passes and carries",
    "formation_in": "shape in possession",
    "formation_out": "shape out of possession",
    "gap_def_mid": "metres between the back line and midfield",
    "line_breaks": "passes that went through at least one opponent line (not round its side)",
    "line_breaks_back": "passes through the opponent's back line",
    "line_breaks_mid": "passes through the opponent's midfield line",
    "line_breaks_fwd": "passes through the opponent's forward line",
    "between_mid_def": "passes received in space between the opponent's midfield and defence",
    "between_fwd_mid": "passes received in space between the opponent's press and midfield",
    "packing": "opponents taken out of the game by passes",
    "between_lines": "passes received in space between any two opponent lines",
    "xt_share_left": "share of the team's threat that came down the left",
    "xt_share_centre": "share of the team's threat that came through the middle",
    "xt_share_right": "share of the team's threat that came down the right",
    "pass_xt_added": "expected threat (xT) the pass added",
    "pass_packing": "opponents the pass took out of the game",
}


class ChatClient(Protocol):
    """The one thing the writer needs from a provider: send two messages, get the reply text.
    Raises on timeouts and errors."""

    def complete(self, system: str, user: str) -> str: ...


class OpenAIChat:
    """`ChatClient` on an `openai` client (AzureOpenAI or OpenAI pointed at GitHub Models)."""

    def __init__(self, client: Any, model: str, timeout_s: float = DEFAULT_TIMEOUT_S):
        self._client, self._model, self._timeout = client, model, timeout_s

    def complete(self, system: str, user: str) -> str:
        reply = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
            timeout=self._timeout,
        )
        return reply.choices[0].message.content or ""


class LLMGenerator:
    name = "llm"

    def __init__(
        self,
        client: ChatClient,
        fallback: TemplateGenerator | None = None,
        max_calls: int = DEFAULT_MAX_CALLS,
        max_retries: int = DEFAULT_RETRIES,
    ):
        self.client = client
        self.fallback = fallback or TemplateGenerator()
        self.max_calls = max_calls
        self.max_retries = max_retries
        self.calls = 0  # model requests made so far (cost guard)
        self._cache: dict[str, Rendered] = {}
        self._lock = threading.Lock()
        self._teams: list[str] = []
        self._players: list[str] = []

    def bind(self, meta: MatchMeta) -> None:
        """Learn which teams and players exist, so invented ones can be caught."""
        self._teams, self._players = known_names(meta)

    # ------------------------------------------------------------------ TextGenerator
    def render(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> tuple[str, str]:
        out = self.render_full(template, mode, lang, slots, claims)
        return out.headline, out.body

    def render_full(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> Rendered:
        key = json.dumps(
            [template, mode, lang, sorted(slots.items()), [(c.key, c.value) for c in claims]]
        )
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        out = self._write(template, mode, lang, slots, claims)
        with self._lock:
            self._cache[key] = out
        return out

    # ------------------------------------------------------------------ internals
    def brief(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> dict[str, Any]:
        """The only thing the model is told."""
        draft = self.fallback.render_full(template, mode, "en", slots, claims)
        return {
            "kind": template,
            "mode": mode,
            "language": lang,
            "names": {k: slots[k] for k in NAME_SLOTS if slots.get(k)},
            "claims": [
                {"key": c.key, "text": fmt(c, lang), "what": _describe(c, slots)} for c in claims
            ],
            "draft_en": {"headline": draft.headline, "body": draft.body},
            "limits": {
                "headline_chars": MAX_HEADLINE_CHARS,
                "body_chars": MAX_BODY_CHARS.get(mode, 300),
            },
        }

    def _take_call(self) -> bool:
        with self._lock:
            if self.calls >= self.max_calls:
                return False
            self.calls += 1
            return True

    def _write(
        self, template: str, mode: Mode, lang: Lang, slots: dict[str, str], claims: list[Claim]
    ) -> Rendered:
        brief = self.brief(template, mode, lang, slots, claims)
        reasons: list[str] = []
        for _ in range(1 + self.max_retries):
            if not self._take_call():
                reasons = [f"cost guard: {self.max_calls} model calls already used for this match"]
                break
            prompt = json.dumps(brief, ensure_ascii=False)
            if reasons:
                prompt += (
                    "\n\nYour previous answer was rejected: "
                    + "; ".join(reasons)
                    + ". Reply again with corrected JSON only."
                )
            try:
                raw = self.client.complete(SYSTEM_PROMPT, prompt)
            except Exception as exc:  # timeouts, auth, rate limits: all the same to the viewer
                reasons = [f"the request failed ({type(exc).__name__})"]
                log.warning("model request failed: %s", exc)
                continue
            parsed = _parse(raw)
            if isinstance(parsed, str):
                reasons = [parsed]
                continue
            headline, body = parsed
            reasons = self.check(headline, body, mode, lang, slots, claims)
            if not reasons:
                return Rendered(headline, body, "model", False)
        log.info("falling back to the template for %s/%s/%s: %s", template, mode, lang, reasons)
        fb = self.fallback.render_full(template, mode, lang, slots, claims)
        return Rendered(fb.headline, fb.body, "template_fallback", fb.translation_unavailable)

    def check(
        self,
        headline: str,
        body: str,
        mode: Mode,
        lang: Lang,
        slots: Mapping[str, str],
        claims: list[Claim],
    ) -> list[str]:
        """Why this text may not air (empty list = it may)."""
        text = f"{headline} {body}"
        reasons = []
        extra = Verifier.unsupported_numbers(text, claims, lang)
        if extra:
            allowed = ", ".join(fmt(c, lang) for c in claims)
            reasons.append(
                f"unsupported number(s) {', '.join(extra)} (the only numbers are: {allowed})"
            )
        bad = name_violations(text, brief_names(slots), self._teams, self._players)
        if bad:
            reasons.append(f"mentions {', '.join(bad)}, who is not in the brief")
        problem = length_problem(headline, body, mode)
        if problem:
            reasons.append(problem)
        return reasons


def _describe(c: Claim, slots: Mapping[str, str]) -> str:
    what = METRIC_WORDS.get(c.metric, c.metric)
    who = slots.get(c.side or "") if c.side else None  # "home" / "away" are name slots
    out = f"{what} ({who})" if who else what
    if c.window:
        out += f", over minutes {c.window[0]}-{c.window[1]}"
    return out


def _parse(raw: str) -> tuple[str, str] | str:
    """(headline, body) from the model's reply, or a sentence saying what is wrong with it."""
    text = raw.strip()
    if text.startswith("```"):  # models sometimes fence their JSON
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return "the reply was not valid JSON"
    if not isinstance(data, dict):
        return "the reply was not a JSON object"
    headline, body = data.get("headline"), data.get("body")
    if not isinstance(headline, str) or not isinstance(body, str):
        return 'the reply must be {"headline": string, "body": string}'
    return headline.strip(), " ".join(body.split())


# ---------------------------------------------------------------------- choosing a provider
def client_from_env(env: Mapping[str, str]) -> tuple[ChatClient | None, str]:
    """(client, status) for the configured provider; client is None when it cannot be built."""
    azure = [env.get(k) for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")]
    azure_key = env.get("AZURE_OPENAI_API_KEY")
    github_token = env.get("GITHUB_TOKEN")
    timeout = float(env.get("WIM_LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    if not (all(azure) and azure_key) and not github_token:
        return None, (
            "no credentials: set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT and "
            "AZURE_OPENAI_API_KEY (or GITHUB_TOKEN for GitHub Models)"
        )
    try:
        from openai import AzureOpenAI, OpenAI  # imported lazily: only needed in llm mode
    except ImportError:
        return None, 'the openai package is not installed (pip install ".[llm]")'
    if all(azure) and azure_key:
        client = AzureOpenAI(
            azure_endpoint=azure[0],
            api_key=azure_key,
            api_version=env.get("AZURE_OPENAI_API_VERSION", AZURE_API_VERSION),
        )
        return OpenAIChat(client, azure[1] or "", timeout), "azure openai / foundry"
    client = OpenAI(
        base_url=env.get("GITHUB_MODELS_ENDPOINT", GITHUB_MODELS_ENDPOINT), api_key=github_token
    )
    model = env.get("WIM_LLM_MODEL", GITHUB_MODELS_DEFAULT_MODEL)
    return OpenAIChat(client, model, timeout), "github models"


def choose_generator(
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[Mapping[str, str]], tuple[ChatClient | None, str]] = client_from_env,
) -> tuple[Callable[[], TextGenerator], str]:
    """(factory that makes a fresh generator per match, one-line status).

    `WIM_GENERATOR=template` (default) is fully offline. `llm` needs credentials; without them it
    says so and stays on templates rather than failing.
    """
    env = os.environ if env is None else env
    wanted = env.get("WIM_GENERATOR", "template").strip().lower()
    if wanted not in ("template", "llm"):
        return TemplateGenerator, f"template (unknown WIM_GENERATOR={wanted!r})"
    if wanted == "template":
        return TemplateGenerator, "template"
    client, status = client_factory(env)
    if client is None:
        return TemplateGenerator, f"template (WIM_GENERATOR=llm but {status})"
    max_calls = int(env.get("WIM_LLM_MAX_CALLS", DEFAULT_MAX_CALLS))

    def build() -> TextGenerator:
        return LLMGenerator(client, max_calls=max_calls)

    return build, f"llm via {status}"

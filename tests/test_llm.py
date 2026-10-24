"""LLM writer: guardrails and fallbacks, tested with fake clients only (no network, no keys)."""

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from whyitmatters.agents import TemplateGenerator, Verifier, Viewer, run_match
from whyitmatters.agents.generator import fmt, render_with_source
from whyitmatters.agents.llm import (
    LLMGenerator,
    OpenAIChat,
    choose_generator,
    client_from_env,
)
from whyitmatters.agents.models import Claim, Draft
from whyitmatters.api import create_app
from whyitmatters.simulator import simulate

SEED = 7


@pytest.fixture(scope="module")
def match():
    return simulate(SEED)


@pytest.fixture(scope="module")
def base(match):
    return run_match(match)


@pytest.fixture(scope="module")
def goal(base):
    return next(c for c in base.cues if c.kind == "goal")


def brief_of(prompt: str) -> dict:
    return json.loads(prompt.split("\n\n")[0])


def caption(brief: dict) -> str:
    """A well-behaved model: names and numbers copied from the brief, in its own words."""
    names = brief["names"]
    who = names.get("player") or names.get("team") or names["home"]
    nums = ", ".join(c["text"] for c in brief["claims"])
    return json.dumps({"headline": f"{who} !", "body": f"{who}: {nums} ({names['home']})"})


class Scripted:
    """Replays canned replies (an Exception is raised, not returned) and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class WellBehaved:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return caption(brief_of(user))


def writer(client, goal, base, **kw):
    gen = LLMGenerator(client, **kw)
    gen.bind(base.state.meta)
    return gen, (goal.slots["template"], goal.slots, goal.claims)


def render(gen, args, mode="fan", lang="fr"):
    template, slots, claims = args
    return gen.render_full(template, mode, lang, slots, claims)


# ------------------------------------------------------------------ the happy path
def test_a_good_answer_airs_in_any_language(goal, base):
    client = WellBehaved()
    gen, args = writer(client, goal, base)
    out = render(gen, args, lang="fr")
    assert out.source == "model" and not out.translation_unavailable
    assert out.body.startswith(goal.slots["player"])
    assert Verifier.unsupported_numbers(f"{out.headline} {out.body}", goal.claims, "fr") == []
    assert len(client.prompts) == 1


def test_decimal_separators_follow_the_language():
    xg = Claim(key="xg", metric="shot_xg", unit="xg", value=0.456, event_id="e")
    assert fmt(xg, "en") == "0.46" and fmt(xg, "ja") == "0.46" and fmt(xg, "xx") == "0.46"
    for lang in ("fr", "de", "pt-BR", "es", "ca", "it", "nl"):
        assert fmt(xg, lang) == "0,46", lang


def test_the_brief_holds_only_names_claims_and_a_reference(goal, base):
    client = WellBehaved()
    gen, args = writer(client, goal, base)
    render(gen, args, lang="fr")
    brief = brief_of(client.prompts[0])
    assert set(brief) == {"kind", "mode", "language", "names", "claims", "draft_en", "limits"}
    assert brief["language"] == "fr" and brief["mode"] == "fan"
    assert set(brief["names"]) <= {"home", "away", "team", "other", "player", "winner", "loser"}
    texts = {c["key"]: c["text"] for c in brief["claims"]}
    assert texts == {c.key: fmt(c, "fr") for c in goal.claims}  # formatted for the language
    raw = client.prompts[0]
    assert (
        "possession_id" not in raw
        and "evidence" not in raw
        and goal.evidence_event_ids[0] not in raw
    )


def test_fenced_json_is_accepted(goal, base):
    nums = ", ".join(fmt(c, "en") for c in goal.claims)
    reply = json.dumps({"headline": "Goal", "body": f"{goal.slots['player']} {nums}"})
    gen, args = writer(Scripted(f"```json\n{reply}\n```"), goal, base)
    assert render(gen, args, lang="en").source == "model"


# ------------------------------------------------------------------ adversarial answers
def good_reply(goal, lang="fr"):
    nums = ", ".join(fmt(c, lang) for c in goal.claims)
    return json.dumps({"headline": "But", "body": f"{goal.slots['player']} {nums}"})


def test_a_wrong_number_is_caught_and_the_retry_sees_why(goal, base):
    bad = json.dumps({"headline": "But", "body": f"{goal.slots['player']} a marqué 99 fois"})
    client = Scripted(bad, good_reply(goal))
    gen, args = writer(client, goal, base)
    out = render(gen, args)
    assert out.source == "model" and len(client.prompts) == 2
    assert "rejected" in client.prompts[1] and "99" in client.prompts[1]


def test_an_english_decimal_point_is_a_wrong_number_in_french(goal, base):
    nums = ", ".join(fmt(c, "en") for c in goal.claims)  # 0.45 instead of 0,45
    reply = json.dumps({"headline": "But", "body": f"{goal.slots['player']} {nums}"})
    gen, args = writer(Scripted(reply), goal, base, max_retries=0)
    assert any("." in fmt(c, "en") for c in goal.claims)
    assert render(gen, args, lang="fr").source == "template_fallback"


def test_an_invented_player_never_airs(goal, base):
    players = [
        p.name for team in (base.state.meta.home, base.state.meta.away) for p in team.players
    ]
    stranger = next(p for p in players if p != goal.slots["player"])
    nums = ", ".join(fmt(c, "es") for c in goal.claims)
    reply = json.dumps({"headline": "Gol", "body": f"{goal.slots['player']} y {stranger}: {nums}"})
    client = Scripted(reply)
    gen, args = writer(client, goal, base)
    out = render(gen, args, lang="es")
    assert len(client.prompts) == 3  # first try + two retries
    assert "not in the brief" in client.prompts[1] and stranger in client.prompts[1]
    expected = TemplateGenerator().render(
        goal.slots["template"], "fan", "es", goal.slots, goal.claims
    )
    assert out.source == "template_fallback" and (out.headline, out.body) == expected
    assert not out.translation_unavailable


def test_a_surname_alone_counts_as_naming_a_player(goal, base):
    players = [
        p.name for team in (base.state.meta.home, base.state.meta.away) for p in team.players
    ]
    stranger = next(p for p in players if p.split()[-1] not in goal.slots["player"])
    nums = ", ".join(fmt(c, "en") for c in goal.claims)
    reply = json.dumps(
        {"headline": "Goal", "body": f"{goal.slots['player']} {nums}. {stranger.split()[-1]}"}
    )
    gen, args = writer(Scripted(reply), goal, base, max_retries=0)
    assert render(gen, args, lang="en").source == "template_fallback"


def test_a_language_without_templates_falls_back_to_flagged_english(goal, base):
    gen, args = writer(Scripted("not json at all"), goal, base)
    out = render(gen, args, lang="ja")
    english = TemplateGenerator().render(
        goal.slots["template"], "fan", "en", goal.slots, goal.claims
    )
    assert out.source == "template_fallback" and out.translation_unavailable
    assert (out.headline, out.body) == english


@pytest.mark.parametrize(
    "reply",
    ["not json", "[]", '{"headline": 1, "body": 2}', '{"headline": "x"}', "", "{"],
    ids=["text", "array", "wrong types", "missing body", "empty", "truncated"],
)
def test_malformed_replies_fall_back(goal, base, reply):
    client = Scripted(reply)
    gen, args = writer(client, goal, base)
    assert render(gen, args, lang="ca").source == "template_fallback"
    assert len(client.prompts) == 3


def test_a_timeout_falls_back_and_is_retried(goal, base):
    client = Scripted(TimeoutError("slow"))
    gen, args = writer(client, goal, base)
    out = render(gen, args, lang="ca")
    assert out.source == "template_fallback" and len(client.prompts) == 3


def test_a_timeout_then_a_good_answer_still_airs(goal, base):
    client = Scripted(TimeoutError("slow"), good_reply(goal))
    gen, args = writer(client, goal, base)
    assert render(gen, args).source == "model"


def test_an_overlong_caption_is_rejected(goal, base):
    nums = ", ".join(fmt(c, "en") for c in goal.claims)
    reply = json.dumps({"headline": "Goal", "body": f"{goal.slots['player']} {nums} " + "x" * 900})
    client = Scripted(reply)
    gen, args = writer(client, goal, base, max_retries=0)
    assert render(gen, args, lang="en").source == "template_fallback"


# ------------------------------------------------------------------ cost guard and cache
def test_the_cost_guard_stops_model_calls(base):
    client = WellBehaved()
    gen = LLMGenerator(client, max_calls=2)
    gen.bind(base.state.meta)
    cues = [c for c in base.cues if c.kind in ("goal", "state_shift")][:5]
    sources = [
        gen.render_full(c.slots["template"], "fan", "fr", c.slots, c.claims).source for c in cues
    ]
    assert len(client.prompts) == 2 and gen.calls == 2
    assert sources[:2] == ["model", "model"] and set(sources[2:]) == {"template_fallback"}


def test_answers_are_cached_per_insight_mode_and_language(goal, base):
    client = WellBehaved()
    gen, args = writer(client, goal, base)
    first = render(gen, args, mode="fan", lang="fr")
    again = render(gen, args, mode="fan", lang="fr")
    assert first == again and len(client.prompts) == 1
    render(gen, args, mode="analyst", lang="fr")
    render(gen, args, mode="fan", lang="de")
    assert len(client.prompts) == 3


# ------------------------------------------------------------------ end to end
def test_a_model_written_match_stays_true_and_says_who_wrote_it(match):
    o = run_match(match, generator=LLMGenerator(WellBehaved()))
    assert o.stats.truth_score >= 0.95 and o.stats.dropped == 0
    assert o.insights and all(i.slots["written_by"] == "model" for i in o.insights)
    trust = o.trust()
    assert trust["written_by_model"] == len(o.insights) and trust["written_by_fallback"] == 0
    for pc in o.personalize(Viewer(mode="fan", lang="fr")):
        assert pc.written_by == "model"
        assert Verifier.unsupported_numbers(f"{pc.headline} {pc.body}", pc.claims, "fr") == []


def test_a_hostile_model_changes_nothing_that_airs(match, base):
    hostile = Scripted(json.dumps({"headline": "Goal 99", "body": "Ten goals, 77 shots"}))
    o = run_match(match, generator=LLMGenerator(hostile))
    assert [c.headline for c in o.cues] == [c.headline for c in base.cues]
    assert [c.body for c in o.cues] == [c.body for c in base.cues]
    assert all(i.slots["written_by"] == "template_fallback" for i in o.insights)
    assert o.trust()["written_by_fallback"] == len(o.insights)
    assert o.recap is not None and o.recap.written_by == "template_fallback"


# ------------------------------------------------------------------ the name check everywhere
def test_the_verifier_rejects_a_draft_that_names_a_player_outside_its_brief(base, goal):
    players = [
        p.name for team in (base.state.meta.home, base.state.meta.away) for p in team.players
    ]
    stranger = next(p for p in players if p != goal.slots["player"])
    nums = ", ".join(fmt(c, "en") for c in goal.claims)
    draft = Draft(
        candidate_id="x", attempt=1, headline="Goal", body=f"{stranger} scores {nums}",
        claims=goal.claims, slots=goal.slots,
    )  # fmt: skip
    verdict = Verifier().run(base.state, draft)
    assert not verdict.ok and verdict.unsupported_names == [stranger]
    honest = draft.model_copy(update={"body": f"{goal.slots['player']} scores {nums}"})
    assert Verifier().run(base.state, honest).ok


def test_the_template_text_always_passes_the_name_check(base):
    verifier = Verifier()
    for cue in base.cues:
        assert verifier.unsupported_names(base.state, f"{cue.headline} {cue.body}", cue.slots) == []


def test_other_languages_get_flagged_english_not_a_crash(base):
    cues = base.personalize(Viewer(mode="fan", lang="de"))
    assert cues and all(c.translation_unavailable and c.written_by == "template" for c in cues)
    english = {c.cue_id: c for c in base.personalize(Viewer(mode="fan", lang="en"))}
    assert all(c.body == english[c.cue_id].body for c in cues)
    spanish_mx = base.personalize(Viewer(mode="fan", lang="es-MX"))
    assert spanish_mx and not any(c.translation_unavailable for c in spanish_mx)
    r = base.recap_for(Viewer(mode="fan", lang="de"))
    assert r.translation_unavailable and "{" not in r.summary
    out = render_with_source(TemplateGenerator(), "recap", "fan", "pt-BR", r.slots, r.claims)
    assert out.translation_unavailable


# ------------------------------------------------------------------ choosing a provider
def fake_openai(monkeypatch):
    made = {}

    class AzureOpenAI:
        def __init__(self, **kw):
            made["azure"] = kw

    class OpenAI:
        def __init__(self, **kw):
            made["openai"] = kw

    monkeypatch.setitem(
        sys.modules, "openai", types.SimpleNamespace(AzureOpenAI=AzureOpenAI, OpenAI=OpenAI)
    )
    return made


def test_template_is_the_default_and_needs_nothing():
    factory, status = choose_generator({})
    assert isinstance(factory(), TemplateGenerator) and status == "template"
    assert choose_generator({"WIM_GENERATOR": "nonsense"})[1].startswith("template (unknown")


def test_llm_without_credentials_stays_on_templates_and_says_why():
    factory, status = choose_generator({"WIM_GENERATOR": "llm"})
    assert isinstance(factory(), TemplateGenerator)
    assert status.startswith("template (WIM_GENERATOR=llm but") and "AZURE_OPENAI" in status


def test_llm_mode_builds_a_fresh_budgeted_writer_per_match():
    client = WellBehaved()
    factory, status = choose_generator(
        {"WIM_GENERATOR": "llm", "WIM_LLM_MAX_CALLS": "5"}, lambda env: (client, "fake")
    )
    a, b = factory(), factory()
    assert isinstance(a, LLMGenerator) and a is not b and a.max_calls == 5
    assert status == "llm via fake"


def test_azure_settings_come_from_the_environment(monkeypatch):
    made = fake_openai(monkeypatch)
    env = {
        "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
        "AZURE_OPENAI_DEPLOYMENT": "writer",
        "AZURE_OPENAI_API_KEY": "test-key-not-real",
    }
    client, status = client_from_env(env)
    assert isinstance(client, OpenAIChat) and "azure" in status
    assert made["azure"]["azure_endpoint"] == "https://example.invalid"
    assert made["azure"]["api_key"] == "test-key-not-real" and "api_version" in made["azure"]
    assert "openai" not in made


def test_github_models_is_the_free_fallback(monkeypatch):
    made = fake_openai(monkeypatch)
    client, status = client_from_env({"GITHUB_TOKEN": "test-token-not-real"})
    assert isinstance(client, OpenAIChat) and "github" in status
    assert made["openai"]["base_url"].startswith("https://") and "azure" not in made
    # Azure wins when both are set
    both = {
        "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
        "AZURE_OPENAI_DEPLOYMENT": "writer",
        "AZURE_OPENAI_API_KEY": "test-key-not-real",
        "GITHUB_TOKEN": "test-token-not-real",
    }
    assert "azure" in client_from_env(both)[1]


def test_a_missing_openai_package_is_reported_not_raised(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)  # makes `import openai` fail
    client, status = client_from_env({"GITHUB_TOKEN": "test-token-not-real"})
    assert client is None and "openai package" in status
    assert client_from_env({})[1].startswith("no credentials")


def test_the_chat_client_asks_for_json_and_returns_the_text():
    calls = {}

    class Completions:
        def create(self, **kw):
            calls.update(kw)
            msg = types.SimpleNamespace(content='{"headline": "a", "body": "b"}')
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    sdk = types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    text = OpenAIChat(sdk, "my-deployment", 7.0).complete("sys", "user")
    assert json.loads(text)["body"] == "b"
    assert calls["model"] == "my-deployment" and calls["timeout"] == 7.0
    assert calls["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in calls["messages"]] == ["system", "user"]


# ------------------------------------------------------------------ the API
def test_health_says_which_writer_is_on():
    assert TestClient(create_app({})).get("/health").json()["generator"] == "template"
    app = create_app({"WIM_GENERATOR": "llm"}, lambda env: (WellBehaved(), "fake"))
    assert TestClient(app).get("/health").json()["generator"] == "llm via fake"


def test_any_language_in_template_mode_returns_flagged_english():
    client = TestClient(create_app({}))
    r = client.get(f"/matches/{SEED}/personal?mode=fan&lang=fr")
    body = r.json()
    assert r.status_code == 200 and body["generator"] == "template"
    assert body["cues"] and all(c["translation_unavailable"] for c in body["cues"])
    assert body["recap"]["translation_unavailable"]
    ca = client.get(f"/matches/{SEED}/personal?mode=fan&lang=ca").json()
    assert not any(c["translation_unavailable"] for c in ca["cues"])


def test_a_language_must_look_like_a_language_code():
    client = TestClient(create_app({}))
    for bad in ("not a language", "x", "en;drop", "e" * 30):
        assert client.get(f"/matches/{SEED}/personal?lang={bad}").status_code == 422, bad


def test_llm_mode_writes_through_the_api_and_reports_it():
    app = create_app({"WIM_GENERATOR": "llm"}, lambda env: (WellBehaved(), "fake"))
    client = TestClient(app)
    body = client.get(f"/matches/{SEED}/personal?mode=fan&lang=fr").json()
    assert body["cues"] and all(c["written_by"] == "model" for c in body["cues"])
    assert not any(c["translation_unavailable"] for c in body["cues"])
    cues = client.get(f"/matches/{SEED}/cues").json()
    assert cues["trust"]["written_by_model"] > 0 and cues["trust"]["written_by_fallback"] == 0

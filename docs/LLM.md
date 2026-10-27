# Model-written captions (`WIM_GENERATOR=llm`)

By default every caption is written by the offline templates (English, Spanish, Catalan): deterministic, instant, no keys. Switching the writer to a hosted model adds **any language** and more natural phrasing, and keeps the same promise: nothing airs unless every number, every name and the length pass the same checks as template text.

## Switch it on

```bash
pip install ".[llm]"                      # the official openai package; nothing else is added
export WIM_GENERATOR=llm
# Microsoft Foundry / Azure OpenAI (preferred):
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="<your deployment name>"
export AZURE_OPENAI_API_KEY="<key>"
# or GitHub Models as a free fallback (used only when the Azure variables are not all set):
export GITHUB_TOKEN="<token with models access>"
```

Try it with one command (any BCP-47 code works for `--lang`):

```bash
python -m whyitmatters.agents --seed 7 --mode fan --lang fr
```

The first line printed says which writer is on (`writer: llm via azure openai / foundry`, or `template (WIM_GENERATOR=llm but …)` when credentials are missing: it never crashes, it stays on templates and says why). Each caption is tagged `[model]` or `[template fallback]`. The app uses the same switch: `uvicorn whyitmatters.api:app --port 8000`, pick a language in the Fan tab (twelve common ones plus “Other…” for any code). `GET /health` reports the writer.

| Variable | Meaning | Default |
| --- | --- | --- |
| `WIM_GENERATOR` | `template` or `llm` | `template` |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY` | Azure OpenAI / Foundry (all three needed) | – |
| `AZURE_OPENAI_API_VERSION` | API version (`2024-10-21` or later) | `2024-10-21` |
| `GITHUB_TOKEN` | GitHub Models fallback | – |
| `GITHUB_MODELS_ENDPOINT` | its OpenAI-compatible endpoint | `https://models.github.ai/inference` |
| `WIM_LLM_MODEL` | model id for GitHub Models | `openai/gpt-4o-mini` |
| `WIM_LLM_MAX_CALLS` | cost guard: model requests per match | `60` |
| `WIM_LLM_TIMEOUT_S` | per-request timeout | `20` |

Keys are only ever read from the environment; nothing in the repository holds one.

Recommended Azure deployment: `gpt-4.1-mini`; `gpt-5-mini` is supported too. Requests use `max_completion_tokens` (accepted by both). GPT-5 and o-series models only take the default temperature: if the service rejects `temperature`, the client retries once without it and stops sending it for that deployment.

## What the model is told

Only a JSON brief: the insight kind, the mode (analyst / fan / player_focus / coach), the target language, the team and player names of that insight, and the verified claims already formatted for that language (decimal separator included: `0,46` in French, `0.46` in Japanese). It also gets `draft_en`, the English template draft, so it knows what each number means. It never sees match events, coordinates or other players. It must answer `{"headline": …, "body": …}`.

## What must be true before anything airs

1. **Numbers.** Every number in the text must match a claim, formatted for the language. (Same check the Verifier applies to template text; ASCII digits only.)
2. **Names.** No known team or player outside the insight's brief may appear, by full name or by surname. The Verifier now applies this to every text, template or model.
3. **Length.** Body at most 300–520 characters depending on mode, headline at most 90.
4. **Retry, then fall back.** A rejected answer is retried up to twice with the reasons in the prompt. After that the offline template takes over: for `en`/`es`/`ca` in that language, for any other language in English with `translation_unavailable` set. Each insight records who wrote what aired (`written_by`: `model`, `template` or `template_fallback`), shown in the Why? drawer, on Fan cues and in the Trust tab.

Not caught, by design: a name the model invents that is not a player or team of the match (the check knows the match's names, not every name in the world); wording quality, tone and translation accuracy. The numbers and the match's names are the part that can mislead.

## Cost guard and cache

At most `WIM_LLM_MAX_CALLS` (60) model requests per match, retries included; after that every caption falls back to the template. Answers are cached by (insight, mode, language), so switching language back and forth costs nothing the second time. A fresh writer, with its own budget and cache, is created for each simulated match.

## Tests

`tests/test_llm.py` uses fake clients only: a well-behaved one, and adversarial ones that return a wrong number, a wrong decimal separator, an invented player, a surname, non-JSON, truncated JSON, wrong types, an overlong caption and a timeout. Each is caught and falls back. No test touches the network or needs a key.

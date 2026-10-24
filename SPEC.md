# SPEC — WhyItMatters

## Problem

A scoreline says what happened, not why. Studio and streaming teams need insight they can put on air live: what changed in the match, why it matters, and proof that it is true. Fans want the same intelligence in their language, about their club and player, at their level of depth.

## Users

| User | Needs |
| --- | --- |
| Studio analyst | Tactical state of the match, the evidence behind every claim, cues timed for graphics |
| Broadcast producer | Fewer, better insights; nothing wrong on air; machine-readable overlay cues |
| Casual fan | Plain-language "why it matters", favourite club and player, own language |
| Data-hungry fan | The numbers: PPDA, field tilt, xG, pass difficulty, speeds |

## Pipeline (the five official stages)

1. **Ingest** — synthetic match events as they happen: passes, carries, shots, tackles, interceptions, pressure, fouls, possession changes, match metadata.
2. **Interpret** — the Match Pulse engine aggregates events into rolling team states: possession share, field tilt, PPDA, tempo, turnover rate, xG flow; classifies each window as `home_control`, `away_control`, `chaos` or `balanced`, and emits state transitions.
3. **Explain** — agents turn transitions and key moments into claims with evidence: Analyst (what is worth saying), Explainer (why it matters), Verifier (every claim checked against match state; rejected claims are rewritten).
4. **Render** — Producer applies an on-air budget and emits timed overlay cues (JSON) plus a full-time recap.
5. **Personalize** — Personalizer reshapes verified insight per mode (analyst, fan, player focus), club, player and language (EN, ES, CA), then re-verifies.

## Data contract

Event coordinates are on a 105 × 68 m pitch **from the acting team's perspective**: every team attacks left to right (`x` 0 → 105). Time is match seconds from kick-off with `period` 1 or 2. See `src/whyitmatters/schema.py`.

The simulator also writes **ground truth**: the scripted phases (`home_control`, `away_control`, `chaos`, `balanced`) with start and end minutes, and key moments (goals, big chances with xG ≥ 0.3). Ground truth is never shown to the agents; it is only used for evaluation.

## Success criteria

Detection is tuned on seeds 0–39 and scored on held-out seeds 1000+ (`python -m whyitmatters.eval --seeds 20 --check`, run in CI).

| Measure | Target | Held-out result (20 matches) |
| --- | --- | --- |
| Phase-shift detection recall (±4 min, correct new state) | ≥ 0.75 | 0.90 |
| Phase-shift detection precision (±4 min, correct new state) | ≥ 0.60 | 0.69 |
| Timeline accuracy (state history with back-dated changes) | ≥ 0.75 | 0.84 |
| Live state accuracy (what the studio sees that minute) | reported | 0.56 |
| Detection lag (true shift → confirmed) | reported | 5.7 min |
| Truth Score (claims passing the Verifier) | ≥ 0.95 after retries | not built yet |
| Insight latency (event → cue) | < 2 s offline, < 6 s hosted model | not built yet |
| Realism per match | 900–1,300 passes, 12–40 shots, 70–90 % completion | ~1,090 passes, ~22 shots, ~80 %, ~2.1 goals |

Known limitation: a shift is confirmed about 5–6 minutes after it starts, because a state needs a 5-minute window and 3 confirming minutes to avoid false alarms. Live claims therefore say "over the last five minutes", and the recap back-dates each shift to its estimated start.

## Non-goals

Real footage or real club data, voice commentary, user accounts, AKS, Fabric.

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

| Measure | Target |
| --- | --- |
| Phase-shift detection recall (±4 min) | ≥ 0.75 across 20 seeds |
| Phase-shift detection precision (±4 min) | ≥ 0.6 across 20 seeds |
| Minute-level state accuracy | ≥ 0.65 |
| Truth Score (claims passing the Verifier) | reported live; target ≥ 0.95 after retries |
| Insight latency (event → cue) | < 2 s offline, < 6 s with a hosted model |
| Realism | per match: 800–1,200 passes, 18–35 shots, pass completion 75–90 % |

## Non-goals

Real footage or real club data, voice commentary, user accounts, AKS, Fabric.

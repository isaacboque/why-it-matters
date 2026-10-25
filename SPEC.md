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
5. **Personalize** — Personalizer reshapes verified insight per mode (analyst, fan, player focus, coach), club, player, metric and language (EN, ES, CA offline; any BCP-47 language with the optional model writer, see [docs/LLM.md](docs/LLM.md)), then re-verifies numbers, names and length.

## Data contract

Event coordinates are on a 105 × 68 m pitch **from the acting team's perspective**: every team attacks left to right (`x` 0 → 105). Time is match seconds from kick-off with `period` 1 or 2. See `src/whyitmatters/schema.py`.

The simulator also writes **ground truth**: the scripted phases (`home_control`, `away_control`, `chaos`, `balanced`) with start and end minutes, and key moments (goals, big chances with xG ≥ 0.3). Ground truth is never shown to the agents; it is only used for evaluation.

## Tactical metrics

Computed per rolling window and per team, from the events the simulator already emits (`src/whyitmatters/pulse/metrics.py`). Coordinates are the acting team's own, so `x >= 52.5` is the opponent's half.

- **Duels** — every tackle (won or lost) and interception; the winner is credited, in their own coordinates, to the defensive (`x < 35`), middle (`35 <= x < 70`) or attacking (`x >= 70`) third; a lost tackle is the ball carrier's win.
- **Duel share by zone** (`duel_share_def|mid|att`) — a team's duels won in a zone ÷ (its wins + the opponent's wins in the mirrored zone, i.e. the same patch of grass); empty when nobody won a duel there.
- **High recoveries** — ball won (tackle won or interception) at `x >= 52.5`; **final-third recoveries** at `x >= 70`.
- **Counter-press recoveries** — ball won back within 5 s of the same team losing it.
- **Own-half losses** — possession lost at `x < 52.5` (dangerous losses): ball won off the team there, or put out of play.
- **Progressive passes** — completed passes that move the ball ≥ 10 m towards goal or from outside into the final third.
- **Long-ball share** — share of a team's passes that travel ≥ 30 m (directness).
- **Central build-up share** — share of build-up passes (`x <= 63`) started in the central third of the pitch width (`22.7 <= y <= 45.3`); the rest is wide.
- **Shots and xG per window** — as before (`shots`, `xg`); **pressures** — the team's pressure events.

**Driver attribution.** When a control shift is confirmed, each driver metric is compared head to head (my number minus theirs; defensive counts per opportunity, i.e. per possession the other side had; PPDA lower is better) between the window before and the window after, normalised by what is a big move for that metric, and the top 2–3 become claims (`dv1`, `dv2`, …) in the explanation. A driver is only named if the number it states is worth stating (e.g. at least 2 high recoveries, PPDA at most 8) and a duel share needs at least 3 duels behind it.

**Build-up of a shot.** The move is the shot's possession; it *began with a recovery* when the event right before it is a tackle won or interception by the shooting team. Goals and big chances say so when the move took 2–20 s from the recovery (counter-press, or high recovery) or contained a completed long ball over the press; the seconds and counts are claims the Verifier recomputes from the raw log.

**Tactical insight kinds** (window of 5 minutes against the 5 before; one per closed minute at most, spaced ≥ 6 min, same kind and team ≥ 15–20 min apart, quiet for 4 min after a voiced control shift):

| Kind | Fires when |
| --- | --- |
| `press_surge` | ≥ 5 high recoveries (≥ 3 more than before) and PPDA at most half the opponent's |
| `midfield_battle` | ≥ 65 % of ≥ 6 midfield duels, after < 55 % |
| `danger_turnovers` | ≥ 6 own-half losses, ≥ 2.5× the opponent's and ≥ 3 more than before |
| `direct_switch` | ≥ 16 % long passes (after ≤ 9 %) over ≥ 15 passes while the opponent presses (PPDA ≤ 6) |
| `pass_difficulty` | hardest completed pass so far (difficulty ≥ 0.8), at most one per 12 min |
| `shot_speed` | fastest shot so far (≥ 110 km/h), at most one per 15 min |

**Viewer controls.** Modes: analyst, fan, player focus, **coach** (the analyst facts plus one rule-based sentence on what the other side could change, e.g. a high press beating short build-up → "going long would bypass it"). **My metric** (pressing, duels, possession, xG, pass quality, speed) keeps one thread; goals always show.

## Shape and value (Analytics v2, part 1)

**Freeze frames.** Every on-ball event carries the positions of all 22 players (`freeze.t` = the acting team, `freeze.o` = the opponents, both in the acting team's coordinates and in each team's `players` order), like StatsBomb 360 data. They are generated in a post-pass that never touches the event generator's random stream: each team plays a role per phase (dominant, dominated, balanced, chaotic) with its own in-possession shape (4-3-3 or 3-2-5), out-of-possession shape (4-4-2 or 4-5-1), back-line height (high 46 m, mid 34 m, low 22 m from goal), width and gap between lines; targets follow the ball, players move at most 8.5 m/s between frames, the acting player stands exactly at the event, plus small noise. The scripted shapes are in `truth.shapes`.

**Team shape** (`pulse/shape.py`), from AVERAGE positions over the window, in and out of possession: formation by line detection (sort the 10 outfield players by depth, a new line wherever the next player is more than 7.5 m deeper, keep 3-4 lines; label = players per line), back-line height, gap between the first two and the last two lines, length, width and compactness (convex hull area). Block type from the out-of-possession line height: high ≥ 30 m, low < 20 m, mid between (set on seeds 0-39).

**Expected Threat** (`pulse/xt.py`): position-based xT (Karun Singh, 2018) on a 16 × 12 grid, fitted on simulated seeds 0-199 by iterating xT(z) = P(shot|z)·mean xG(z) + P(move|z)·Σ T(z→z')·xT(z'), where T counts only successful moves. xT added = xT(end) − xT(start) for every completed pass and carry; summed per team, per window, per minute (momentum) and per 6 × 3 zone (damage map). Fitted on the simulator's football: the method is unchanged with real event data.

All of these are window metrics the Verifier recomputes by replaying the raw log, freeze frames included; a formation travels in a claim as a number (442 → "4-4-2").

## Success criteria

Detection is tuned on seeds 0–39 and scored on held-out seeds 1000+ (`python -m whyitmatters.eval --seeds 20 --check`, run in CI).

| Measure | Target | Held-out result (20 matches) |
| --- | --- | --- |
| Phase-shift detection recall (±4 min, correct new state) | ≥ 0.75 | 0.87 |
| Phase-shift detection precision (±4 min, correct new state) | ≥ 0.60 | 0.67 |
| Timeline accuracy (state history with back-dated changes) | ≥ 0.75 | 0.82 |
| Live state accuracy (what the studio sees that minute) | reported | 0.56 |
| Detection lag (true shift → confirmed) | reported | 5.4 min |
| Truth Score (claims passing the Verifier) | ≥ 0.95 after retries | 1.00 with the offline generator; 0.92 raw at 30 % injected faults, with on-air accuracy 1.00 after retries (seeds 0–19) |
| Formation detection, out / in possession (5-min windows inside a scripted phase) | ≥ 0.70 / ≥ 0.85 | 0.75 / 0.92 |
| Block type (high / mid / low) | ≥ 0.65 | 0.76 |
| Driver attribution (a pressing metric among the top-3 drivers of a correct control shift) | ≥ 0.70 | 0.71 on seeds 0–19 (tuning), 0.79 on held-out seeds 1000–1019 |
| Insight latency (event → cue) | < 2 s offline, < 6 s hosted model | 6.4 ms mean, 159 ms max per insight |
| Realism per match | calibrated to public league averages (docs/DATA.md) | ~932 passes, ~94 long balls, ~2.7 goals, ~21 shots, 78 % completion |

Known limitation: a shift is confirmed about 5–6 minutes after it starts, because a state needs a 5-minute window and 3 confirming minutes to avoid false alarms. Live claims therefore say "over the last five minutes", and the recap back-dates each shift to its estimated start.

## Non-goals

Real footage or real club data, voice commentary, user accounts, AKS, Fabric.

# why-it-matters: Analytics v2 + UI v2 (spec by Cowork, approved by Isaac 2026-10-25)

Isaac's brief (his words, translated): the mock is great, now make it a professional product
that makes you say "wow, a pro built this"; evaluate many more metrics; which passes and which
zones are doing damage; how teams are positioned tactically; as complete as possible.
Rules that still hold: synthetic, fictional data only; no league marks, logo, name or typeface
(colours only); every number on screen is a Verifier-checked Claim; new code only.

---------------------------------------------------------------------------------------------
## PART A. Analytics v2
---------------------------------------------------------------------------------------------

### A0. Data foundation: freeze frames (biggest unlock, do first)
Event data alone cannot say where teams stand. Add StatsBomb-360-style freeze frames to the
simulator: for every on-ball event, the (x, y) of all 22 players (+ the ball), in a compact
array form. Generate them from:
- each team's formation with separate IN-possession and OUT-of-possession shapes
  (e.g. 4-3-3 that builds up as 3-2-5 when dominant; 4-4-2 / 4-5-1 block when defending),
- phase style (scripted ground truth): defensive line height and block (high / mid / low),
  width, compactness, press triggers; dominated teams drop deeper and narrower,
- ball-side shift and ball-oriented compaction, plus small noise,
- continuity between frames (players move at plausible speeds, max ~9.5 m/s).
Record the scripted shape per phase as ground truth (formation label, block height) so shape
detection can be evaluated. Keep the realism tests green. Size: keep a full match JSONL < 6 MB;
the static demo may subsample frames.
This also enables physical data: distance covered, sprints (> 25 km/h), high-intensity runs,
top speed, per player and per team per window (the hackathon rules list "speed and distance
indicators triggered when thresholds are reached").

### A1. Value model: Expected Threat (xT)
- Fit a position-based xT grid (16 x 12) on simulated matches, seeds 0-199, by the standard
  Markov iteration: xT(z) = P(shoot|z)*P(goal|shoot,z) + P(move|z) * sum_z' T(z->z') xT(z').
  Ship the fitted grid as JSON in the repo; document it in METRICS.md.
- Every completed pass and carry gets xT added = xT(end) - xT(start).
- Derived: xT generated per team / player / zone / window; xT momentum per minute (the
  broadcast "momentum" chart); most valuable actions of the match; xG chain and xG build-up
  per player (involvement in possessions that end in a shot).

### A2. Progression and penetration (which passes hurt)
- Progressive passes and carries (exists), passes into the final third, into the box, into
  zone 14 and the two half-spaces; final-third entries by channel (left / left half-space /
  centre / right half-space / right).
- Line-breaking passes (needs A0): completed, >= 10% closer to goal, and either split two
  defenders within ~10 m of each other or end behind a defensive line (Hudl StatsBomb
  definition).
- Packing (needs A0): number of opponents bypassed (between ball and goal at start, not at end).
- Receptions in space / between the lines: distance from the receiver to the nearest
  defender, buckets 0-2, 2-5, 5-10, 10+ m; receptions between the opponent's defensive and
  midfield lines.
- Switches of play, cut-backs (pass from the by-line zone back to the central box), through
  balls (into space behind the line), crosses.
- "Most damaging passes": top passes by xT added, with origin -> destination drawn on the pitch.

### A3. Damage maps (which zones hurt)
- 18-zone grid (6 lengths x 3 widths) and 5-channel view: xT generated and conceded per zone.
- Insights: "70% of their threat comes down our left half-space", "they keep finding the gap
  in zone 14", "every attack goes wide and dies there".

### A4. Team shape (how teams are positioned) — needs A0
- Average positions in and out of possession per window; detected formation (assign players to
  template slots, report the nearest template and a confidence); shape changes over time.
- Defensive line height, team length and width, compactness (convex hull area), distance
  between lines (defence-midfield, midfield-attack): "the gap between their lines has grown
  from 9 to 17 m".
- Block type (high / mid / low) and pressing height.
- Pass network: nodes at average positions sized by involvement, edges by completed passes
  (>= 3), the hub player (betweenness), the side the team favours.
- Evaluate formation and block detection against the simulator ground truth (report accuracy).

### A5. Pressing and defending (extend what exists)
- PPDA, high recoveries, counter-press (exist); press success (pressure followed by a
  turnover within 5 s), pressing traps (side of the pitch where regains happen), how the
  opponent escapes the press (long, short through the middle, wide), defensive actions map.

### A6. Chances
- Shot map with xG, xG per shot, shot type from the assist (cut-back, through ball, cross,
  long shot), big chances, xG flow, finishing vs xG. Optional: corners and free kicks in the
  simulator if cheap.

### A7. Players
- Transparent rating 1-10 (xT added + defensive value + chance creation + losses), with the
  breakdown visible; player card: involvement, xT added, progressive actions, line-breaking
  passes, key passes / xA, duels, distance, top speed, sprints.

### A8. Insight kinds to add (each with fan + analyst + coach phrasing, en/es/ca, LLM-ready)
zone_damage, line_breakers (a player or team breaking lines repeatedly), shape_change
("they've dropped into a back five"), lines_stretched (gap between lines grows), block_drop
(defensive line drops X m), hub_player (pass-network hub), press_escape (how they beat the
press), physical_drop (team distance / intensity falling late), momentum_swing (xT momentum),
most_dangerous_pass. Every number is a Claim; the Verifier must be able to recompute each new
metric from the raw log (+ freeze frames). Repeat limits per kind; Producer budget unchanged.

### A9. Explaining it (two depths, always)
For every metric in docs/METRICS.md add: one-line fan meaning, analyst definition, why it
matters, a glossary "?" text (en/es/ca), and which insight kinds use it. Fan copy states the
meaning first and at most one number; analyst copy names the metric, the number and the
comparison (before/after, vs opponent, vs match average).

---------------------------------------------------------------------------------------------
## PART B. UI v2: broadcast-grade product
---------------------------------------------------------------------------------------------
Quality bar: it should look like a product from a top sports-data / broadcast graphics company,
not a hackathon mock. Use the `frontend-design` skill if it is available. No build step is
still preferred (plain JS + canvas/SVG); Google Fonts allowed.

Direction: "matchday control room". Keep the purple / green / magenta / cyan palette. Dark
studio theme by default for Studio and Broadcast (deep purple surfaces, neon accents used
sparingly for data), light theme for Fan reading; both from one token set. Typography: a
condensed display face for scorebug, numbers and headlines (e.g. Barlow Condensed or Saira
Condensed), a clean sans for text (e.g. IBM Plex Sans), a mono for IDs; tabular figures
everywhere numbers align. Fictional club crests: generated SVG shields with initials and club
colours (never real crests).

Layout:
1. Global scorebug bar (broadcast style): crests, short names, score, running clock, thin
   possession bar, momentum sparkline, Truth Score seal.
2. Match Centre (was Studio), desktop 3 zones:
   - Pitch with a LAYER switcher: Live actions | Average shape (in / out of possession) |
     Pass network | Damage zones (xT) | Shot map | Heatmap | Most dangerous passes.
     Smooth transitions between layers; tooltips on hover; legend per layer.
   - Timeline scrubber under the pitch: play/pause, speed, jump to minute; markers for goals,
     control shifts, chaos; the whole page re-renders at the scrubbed minute.
   - Momentum chart (xT momentum bars per minute, phase bands for control / chaos, goal markers)
     and a head-to-head stat block with mirrored bars (possession, xG, xT, field tilt, PPDA,
     duels by zone, progressive, line-breaking, distance, sprints), each with the "?" glossary.
   - Insight feed as broadcast cards: kind icon, minute, verified seal, priority, a mini-viz per
     card showing its driver (sparkline / mini-pitch / bar), "Why?" drawer redesigned as a
     clean evidence sheet.
3. Broadcast (new tab): a 16:9 frame with a top-down "tactical camera" of the match and the cue
   overlays rendered as lower-thirds / corner bugs using t_in / t_out from the cue JSON. This
   shows the Render stage literally ("synchronised graphical overlays on a live match feed").
4. Fan: mobile-first story feed: big type, one hero number per card, sticky personalization
   chips (language, mode, club, player, my metric), "for you" highlight, player card sheet.
5. Players (new tab): sortable table + player cards with rating breakdown and mini radar.
6. Trust: control-room layout: Truth Score gauge, claims checked/rejected, latency histogram,
   verifier log table with filters, benchmark section clearly labelled.
Craft: loading skeletons, empty states, 150-250 ms transitions, prefers-reduced-motion,
keyboard navigation, visible focus, ARIA on tabs/dialogs, responsive at 390 / 768 / 1440,
no horizontal scroll, light/dark, consistent spacing scale and radii, icons as inline SVG.
Static demo export must include everything the new UI needs (shape, networks, xT, frames,
subsampled) and stay under 15 MB.

---------------------------------------------------------------------------------------------
## Order, cut-lines and verification
---------------------------------------------------------------------------------------------
Deadline Tue 27 Oct 22:00 Madrid. Ship as several PRs, each green and merged:
1. A0 freeze frames + A4 shape + A1 xT (the foundation and the most visible wins)
2. A2 + A3 + A8 subset (line-breaking, zone damage, shape_change, lines_stretched, momentum_swing)
3. UI v2 Match Centre + scorebug + layers + timeline
4. UI v2 Broadcast tab + Fan + Players + Trust
5. Remaining metrics (A5-A7 extensions, physical) and insight kinds
If time runs short, cut from the bottom. `node` is not available in the unattended run: Cowork
does the visual QA (headless browser screenshots) after each UI PR merges and queues fixes.

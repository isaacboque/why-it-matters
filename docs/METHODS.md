# Methods sheet

Every number WhyItMatters puts on screen comes from one of the methods below. For each one this sheet gives the formula, our parameters, where the definition comes from, the test that pins it down and how it is validated. Data format and calibration are in [DATA.md](DATA.md).

## How we know it's right

1. **Published definitions.** Where the football analytics community already has a definition, we use it and cite it: Expected Threat, line-breaking passes, PPDA. Where we simplified one, this sheet says so.
2. **Open code and unit tests on hand-built plays.** Each metric has tests on small event sequences built by hand, so the expected answer is known exactly (for example: "this interception 4 s after losing the ball is a counter-press recovery").
3. **Evaluation against planted ground truth.** The simulator knows what really happened: who controlled each phase, which shape each team played, which chances mattered. We measure the engine against it on held-out matches, and CI fails if any score drops below target. This is not possible with real data, where nobody knows the truth.
4. **Every number is traceable.** Each on-screen claim carries the event ids behind it; the "Why?" sheet in the app shows them.
5. **The Verifier.** Before anything airs, an independent agent recomputes every claimed number from the raw event log, freeze frames included, and rejects any number in the text that no claim supports. With a model that deliberately mis-states 30 % of first drafts, 0.93 of all generated claims are true, yet on-air accuracy stays at 1.00 because every wrong draft is caught and rewritten.

All coordinates below are the acting team's own: attacking left to right, x = 0 own goal line, 105 × 68 m pitch.

## Match state (Match Pulse)

Computed over a rolling 5-minute window (`pulse/metrics.py`, `pulse/engine.py`).

| Metric | Formula and parameters | Source | Test |
| --- | --- | --- | --- |
| Possession share | in-play seconds with the ball / all in-play seconds; gaps > 20 s are dead ball | standard | `tests/test_pulse.py::test_indices_in_range` |
| Pass completion | completed / attempted passes | standard | `tests/test_simulator.py::test_realistic_volumes` |
| Field tilt | team's passes made at x ≥ 70 / both teams' passes at x ≥ 70 | common analytics definition | `tests/test_pulse.py::test_indices_in_range` |
| PPDA | opponent passes in their own 60 % (x ≤ 63) / our defensive actions (tackles, interceptions, fouls) at x ≥ 42; lower = harder press | Colin Trainor's PPDA, as widely used | `tests/test_pulse.py::test_ppda_counts_only_press_zone_actions` |
| Turnovers per minute | open-play losses (ball won by the opponent, or put out) per minute, both teams | ours | `tests/test_tactics.py::test_own_half_losses_are_dangerous_losses` |
| Dominance index | 0.5 × (2 × possession − 1) + 0.5 × (2 × completion gap), smoothed by an exponential moving average with weight 0.6 on the newest minute; in [−1, 1] | ours; field tilt was tested and dropped as too noisy | `tests/test_pulse.py::test_classify_thresholds` |
| Chaos index | 0.5 × clip((turnovers/min − 2) / 3.5) + 0.5 × clip((0.82 − mean completion) / 0.27); in [0, 1] | ours | same |
| State | chaos if chaos ≥ 0.55; else home/away control if dominance ≥ +0.25 / ≤ −0.25; else balanced. A change is confirmed after 3 consecutive minutes and back-dated by half a window | ours | `tests/test_pulse.py::test_transitions_change_state_and_cite_evidence` |

**Validation.** On 20 held-out matches (seeds 1000+), a shift is counted as detected when it is confirmed within ±4 minutes with the correct new state. Results: recall 0.87, precision 0.67, timeline accuracy 0.82, mean confirmation lag 5.4 minutes. Run `python -m whyitmatters.eval --seeds 20 --check` to reproduce.

**Known limitation.** The confirmation lag is the price of avoiding false alarms. Live claims therefore say "over the last five minutes".

## Tactical metrics

| Metric | Formula and parameters | Source | Test |
| --- | --- | --- | --- |
| Duels won by zone | every tackle (won or lost) and interception; the winner is credited in their own third (defensive x < 35, middle, attacking x ≥ 70) | ours | `tests/test_tactics.py::test_duels_credit_the_winner_in_their_own_third` |
| Duel share by zone | our wins in a zone / (our wins + opponent wins on the same patch of grass, i.e. the mirrored third) | ours | `tests/test_tactics.py::test_duel_share_pairs_a_teams_attacking_third_with_the_others_defensive_third` |
| High / final-third recoveries | ball won (tackle won or interception) at x ≥ 52.5 / x ≥ 70 | in the spirit of Opta's "high turnovers" | `tests/test_tactics.py::test_recoveries_high_and_in_the_final_third` |
| Counter-press recoveries | ball won back within 5 s of the same team losing it | ours | `tests/test_tactics.py::test_counter_press_needs_the_ball_back_within_five_seconds` |
| Own-half losses | possession lost at x < 52.5 | ours | `tests/test_tactics.py::test_own_half_losses_are_dangerous_losses` |
| Progressive passes | completed passes that move the ball ≥ 10 m towards goal, or from outside into the final third | **simplified.** Providers use distance rules that grow with distance from goal; aligning to one is proposed, not done | `tests/test_tactics.py::test_progressive_passes_move_the_ball_towards_goal_or_into_the_final_third` |
| Long-ball share | passes ≥ 30 m / all passes | ours; Opta counts long balls at 32 m, and the calibration table uses 32 m | `tests/test_tactics.py::test_long_ball_and_central_buildup_shares` |
| Central build-up share | build-up passes (x ≤ 63) started in the central third of the width / all build-up passes | ours | same |

**Driver attribution.** When a control shift is confirmed, each tactical metric is compared head to head (ours minus theirs) between the window before and the window after. Defensive counts are judged per opponent possession, and each change is normalised by what counts as a big move for that metric. The top 2-3 changes become the "why" in the explanation, each a claim the Verifier checks.

Validation: in control phases, the scripted dominant team presses (press 0.7 against 0.1), so a pressing metric should be among the drivers. It is in 0.71 of correctly detected shifts on tuning seeds 0-19, and 0.79 on held-out seeds 1000-1019 (`tests/test_tactics.py::test_driver_attribution_finds_the_scripted_press`).

## Chances

| Metric | Formula and parameters | Source | Test |
| --- | --- | --- | --- |
| xG | logistic(−1.25 + 1.6 × opening angle to the posts (rad) − 0.09 × distance to goal (m)); × 0.7 under pressure; clipped to [0.01, 0.95] | distance + angle is the textbook first xG model; coefficients ours, calibrated so goals per match match the league average | `tests/test_simulator.py::test_xg_is_monotonic_with_distance` |
| Big chance | a shot with xG ≥ 0.3 | common threshold | `tests/test_agents.py::test_analyst_finds_every_goal_and_big_chance` |
| Build-up of a shot | the shot's possession; it began with a recovery when the event before it is a won tackle or interception by the shooting team; seconds from recovery to shot; completed long balls in the move | ours | `tests/test_tactics.py::test_buildup_reads_a_high_recovery_followed_by_a_long_ball` |

## Value: Expected Threat (xT)

Position-based xT, introduced by [Karun Singh in 2018](https://soccermatics.readthedocs.io/en/main/lesson4/xTPos.html).

- **Grid:** 16 × 12 cells.
- **Fit:** on simulator seeds 0-199 (`pulse/xt.py`, grid shipped as `pulse/xt_grid.json`).

```text
xT(z) = P(shot | z) · mean xG of shots from z + P(move | z) · Σ_z' T(z → z') · xT(z')
```

- **Moves:** passes and carries.
- **T(z → z'):** the share of moves from z that succeed and end in z'. Failed moves add nothing.
- **Solving:** iterate 40 times from zero.
- **Value of an action:** xT added = xT(end) − xT(start), for completed passes and carries.
- **Sums:** per team and window, per minute (the momentum chart) and per 6 × 3 zone (the damage map).

Tests: `tests/test_shape.py::test_xt_grows_towards_goal` and `tests/test_shape.py::test_xt_added_is_end_minus_start`.

**Known limitation.** The grid is fitted on simulated matches, so its values describe the simulator's football. The method is the same with real event data; only the input changes. Refit with `python -m whyitmatters.pulse.xt --fit --seeds 200`.

## Damage: which passes hurt

Computed per completed pass from its freeze frame, then summed per team and window (`pulse/damage.py`). All in the passer's coordinates.

| Metric | Formula and parameters | Source | Test |
| --- | --- | --- | --- |
| Packing | opponent outfield players standing goal-side of the passer and behind the reception point (start x < opponent x < end x), on the pass's frame | after Impect's packing; one frame, not tracked through the pass | `tests/test_damage.py::test_packing_counts_the_opponents_a_pass_goes_past` |
| Line-breaking pass | completed, ends ≥ 10 % closer to the centre of goal, and the pass segment crosses an opponent line's mean depth at a y inside that line's lateral span (outermost players, ± 2 m). Reported per line broken: back, midfield, forward. Passes round the side of a line do not break it | after Hudl StatsBomb's line-breaking passes, **simplified**: lines come from one freeze frame, not from who the ball passes between | `tests/test_damage.py::test_pass_round_the_outside_of_the_back_four_does_not_break_it` and the four tests after it |
| Reception between the lines | completed pass received between any two consecutive opponent lines (midfield-defence `between_mid_def`, press-midfield `between_fwd_mid`, plus the extra gap when 4 lines are detected), inside the two lines' lateral span (± 2 m) and ≥ 3 m from every opponent in the frame (a reception in space). `between_lines` is the total | common analyst definition, **simplified** to one frame | `tests/test_damage.py::test_reception_in_the_pocket_behind_the_midfield_is_mid_def` and the three tests around it |
| Box, zone 14, half-space entries | completed pass or carry that ends in the area from outside it. Box: x ≥ 88.5, 13.84 ≤ y ≤ 54.16. Zone 14: 70 ≤ x < 88.5, middle third of the width. Half-spaces: final third, between the box edge and the middle third | standard pitch zones | `tests/test_damage.py::test_zone_entries_and_lanes` |
| Threat by lane | share of the team's positive xT that ended in the left, central or right third of the width (y = 0 is the attacking team's left) | ours | `tests/test_damage.py::test_window_damage_metrics` |
| Most dangerous pass | the completed pass with the largest xT added | ours, on Karun Singh's xT | same |

Lines come from a single freeze frame: `detect_lines` splits the opponent outfield players by depth gaps and forces 3 or 4 lines (merging the closest or splitting the deepest), so a "line" is a snapshot of the block, not a tracked unit. Constants: `CLOSER_SHARE` 0.10, `LINE_SPAN_MARGIN_M` 2 m, `RECEPTION_SPACE_M` 3 m.

Rates per team per match on simulator seeds 0-19 (about 360 completed passes per team per match): line-breaking passes 81 (23 % of completed passes; was 98, 27 %, under the mean-depth rule), of which through the back line 40, midfield line 43, forward line 20 (a pass can break several); receptions between the lines 131 (36 %; 74 mid-def, 55 press-midfield, 2 in the extra gap), which is higher than before (112) because every pair of lines now counts; packing 557 (1.55 opponents per completed pass, unchanged). These are simulator rates; no external benchmark is cited.

## Damage and shape insights

The Tactics agent compares the last 5 minutes with the 5 before (`agents/tactics.py`). Thresholds were set on seeds 0-39; one tactical insight at most every 6 minutes, with a per-kind cooldown.

| Insight | Fires when | Claims the Verifier checks |
| --- | --- | --- |
| Playing through the lines | ≥ 9 line-breaking passes, ≥ 4 more than the opponent and ≥ 4 more than the window before | line-breaking passes, receptions between the lines |
| Danger down one lane | xT ≥ 0.15, ≥ 1.5 × the opponent's, and ≥ 60 % of it down one flank (80 % through the middle, where most threat goes anyway) | lane share, xT |
| Momentum swing | xT ahead by ≥ 0.12 after being ≥ 0.05 behind in the window before | both teams' xT |
| Change of shape | the in-possession formation over the last 8 minutes differs from the 8 before, and the windows ending 2 minutes earlier agree with each reading | formation now and before |
| Stretched lines | out of possession, the gap between back line and midfield ≥ 16.5 m and ≥ 3 m wider than before, with the team ≥ 33 m long | gap now and before |
| The pass that broke it open | a completed pass adds ≥ 0.09 xT and bypasses ≥ 3 opponents | xT added, opponents bypassed |

**Validation.** Shape changes are planted by the simulator, so they can be checked: 0.84 of reported changes (43/51) match a scripted change of shape in possession on held-out seeds 1000-1019. Stretched lines fall inside a scripted broken (chaos) spell, where the simulator opens the gap to 17 m, in 0.77 of cases (10/13). Tests: `tests/test_damage.py::test_shape_changes_match_the_planted_shapes` and `tests/test_damage.py::test_stretched_lines_come_from_broken_games`.

## Freeze frames

Positions of all 22 players at every on-ball event (`simulator/positions.py`). They are generated in a post-pass that never touches the event generator's random stream.

Each team plays a role per phase. The role sets its shape in possession (4-3-3, or 3-2-5 when dominant) and out of possession (4-4-2, or a 4-5-1 low block when dominated), its back-line height (high 46 m, mid 34 m, low 22 m from goal), its width and the gap between lines (17 m when the game is chaotic).

From the role, each frame is built in four steps:

1. **Targets follow the ball.** The back line never stands in front of a ball near its own goal, and the block shifts sideways towards the ball.
2. **Players move at human speed.** Each moves towards its target at most 8.5 m/s between frames.
3. **The actor is placed exactly.** The acting player stands at the event location.
4. **Noise.** About 1 m of persistent noise per player, plus about 1 m of jitter per frame.

Tests: `tests/test_shape.py::test_players_move_at_human_speeds` and `tests/test_shape.py::test_actor_stands_at_the_event`.

## Team shape

All shape metrics come from average positions over the window, in and out of possession (`pulse/shape.py`).

| Metric | Formula and parameters | Test |
| --- | --- | --- |
| Formation | sort the 10 outfield players by depth; start a new line wherever the next player is more than 7.5 m deeper; merge or split to keep 3-4 lines; the label counts players per line from back to front | `tests/test_shape.py::test_templates_are_detected` |
| Line height | mean depth of the back line, metres from own goal | `tests/test_shape.py::test_shape_summary_numbers` |
| Gaps between lines | first-to-second line and second-last-to-last line, in metres | same |
| Length, width | spread of the outfield players | same |
| Compactness | convex-hull area of the outfield players, m² | `tests/test_shape.py::test_hull_area_of_a_square` |
| Block | out-of-possession line height: high ≥ 30 m, low < 20 m, otherwise mid (set on seeds 0-39) | `tests/test_shape.py::test_block_thresholds` |

**Validation.** On 5-minute windows inside a scripted phase on held-out seeds:

| Measure | Result | Target |
| --- | --- | --- |
| Formation out of possession | 0.75 | ≥ 0.70 |
| Formation in possession | 0.92 | ≥ 0.85 |
| Block type | 0.76 | ≥ 0.65 |

Run `python -m whyitmatters.eval --seeds 20 --check` to reproduce.

## Trust

| Measure | Definition | Test |
| --- | --- | --- |
| Truth Score | claims that matched the match state / all claims generated, across all drafts | `tests/test_agents.py::test_end_to_end_truth_and_budget` |
| On-air accuracy | every claim that aired, re-checked against the final match state | `tests/test_agents.py::test_a_generator_that_always_lies_never_reaches_air` |
| Unsupported number | any number in a text that no claim accounts for, formatted for the viewer's language | `tests/test_agents.py::test_verifier_rejects_an_invented_number` |

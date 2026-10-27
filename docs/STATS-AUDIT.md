# Stats audit

Every number the UI and the API show was recomputed from the raw event log by a checker that shares no code with the product (`tests/test_stats_audit.py`: it imports nothing from `whyitmatters.pulse`, and reads only the events and the xT grid file). It runs over seeds 0-19 (tuning) and 1000-1019 (held out, the ones `eval` uses). About 95 metrics are checked, per team, per minute, in both the 5-minute window and the whole-match scope; every claim the Verifier signs (insights and recaps, all 40 matches) is checked against the independent value too.

## Result

| Metric | Where shown | Check | Before → after | Pinned by |
| --- | --- | --- | --- | --- |
| Match clock, halves | scorebug clock ("first / second half", FT), momentum chart, every `minute` | `t` never goes back; first half < 45:00, second half starts at 45:00; `minute` = floor(`t`/60); 1-5 min added | **Discrepancy.** Up to two first-half events per match (the last move, or the kick-off after a late goal) were stamped after 45:00, so the second half's 45:00 kick-off went back in time and the replay (sorted by `t`) showed them out of order. A stamp such as `t = 60.0` could also be `minute 0` (minute taken before rounding). → Both fixed in `simulator/engine.py` | `test_clock_and_halves` |
| Score | scorebug, broadcast bug, recap, personal recap (4 modes × en/es/ca), goal lower thirds | running count of `goal` shots equals `score_*` on every event, the final recap and every goal cue headline; replay delivers events in order | Consistent; the replay order issue above could have made the bug show an older score for a moment → fixed with the clock | `test_score_everywhere_equals_goal_events`, `test_personal_recap_score` |
| Possession share, pass accuracy, passes | scorebug, head-to-head, recap | every minute, both scopes | Consistent | `test_every_window_and_match_scope_matches_independent` |
| Shots, shots on target, xG | scorebug, head-to-head, players tab | totals from the log; xG to 2 dp | Consistent | `test_shots_on_target_xg_and_accuracy_totals` and the window test |
| Progressive passes, field tilt, PPDA, tempo, losses/min, turnovers/min | head-to-head, cues | independent recount | Consistent | window test |
| Duels by zone, duel shares, high recoveries, final-third recoveries, counter-press, own-half losses | head-to-head, cues | independent recount from the definitions in `pulse/metrics.py` | Consistent | window test |
| xT, xT per minute, xT by lane | momentum chart, head-to-head, cues | grid read from `xt_grid.json`, own cell maths | Consistent | window test, claims test |
| Line-breaking passes (total, back / midfield / forward), packing, receptions between the lines (total, mid-def, fwd-mid), box / zone 14 / half-space entries | head-to-head, cues, players tab | own line detection, lateral-span rule and reception-in-space rule, rebuilt from the definitions in `pulse/damage.py`'s docstring | Consistent, with one float artefact: `damage.py` flips the opponents' frame twice (`68 - (68 - y)`), so a reception that lands exactly on a lateral-span edge (1-decimal data, e.g. y = 2.1 against a span edge of 4.1 - 2) can be a ulp off and be left out. About 1 pass in 10,000; the test allows for exactly those counted cases. Not changed here (`damage.py` belongs to another change); a one-line fix is to compare with a 1e-9 margin | window test |
| Formation labels, line height, gaps, length, width | scorebug, shape layer, cues | own average-position and line detection, 8-frame minimum | Consistent | window test, claims test |
| Head-to-head "window" vs "match" | head-to-head toggle | `home`/`away` = minutes m-4..m, `match` = minutes 0..m, for every m; at full time `match` = whole log | Consistent: the scopes use the right ranges | window test |
| Players tab | players table, stand-outs | per-player passes, completions, shots, goals, xG, ball wins, line breaks, bypassed, xT summed per team equal the team totals; per-player counts equal the log; the table's sort is descending; the squad plays all 90 minutes (no substitutions, no events from outside the 22), so there is no minutes column to check | Consistent. xT is rounded per pass before the table adds it up, so a player-sum can differ from the team total by a few thousandths (tolerance 0.36 in the test; observed far smaller) | `test_players_tab_sums_equal_team_totals` |
| Verifier claims | "Why?" drawer, trust ledger | every claim of every insight and recap, every claim metric, stated value within the claim's own tolerance of the independent value | Consistent (no claim differs) | `test_every_verifier_claim_equals_independent_value` |
| Pressing, chances, pass network, physical (`press_wins`, `press_success`, `regains`, `regains_wide_share`, `press_escapes_short/long`, `press_escapes`, `press_escape_rate`, `big_chances`, `xg_per_shot`, `finishing`, `shots_cutback/cross/through/long`, `hub_share`, hub player, `distance_per_min`, `sprints`, `high_speed_runs`, `top_speed_kmh`) | head-to-head, cues, Why? drawer | rebuilt in `tests/depth_indep.py` from the definitions in `docs/METHODS.md` (own checkpoint walk, own shot-kind and escape rules; the line and reception rules come from the already independent ones above), every minute, window and match scope, both teams | New in this change. Consistent with no discrepancy; the escape and through-ball counts share the line-edge allowance above | `test_every_depth_metric_matches_the_independent_recount` |
| Player cards and rating | `GET /matches/{seed}/players` | per-player counts, key passes and xA, distance, top speed and sprints rebuilt from the log; the rating recomputed from the stated weights; per-player sprints sum to the team's, key passes to the team's assisted shots | New. Consistent (rating within 0.1 of the independent value, the slack for per-pass xT rounding) | `test_player_cards_match_the_independent_recount_and_sum_to_the_team` |
| New insight kinds (`block_drop`, `hub_player`, `press_escape`, `physical_drop`) | cues, Why? drawer | every claim of every insight equals the independent value, `player_involvement` included (all 40 matches) | Consistent | `test_every_verifier_claim_equals_independent_value` |
| Shots per team | head-to-head, scorebug | Premier League reference below | **Discrepancy.** 10.4 against 12.5-13.8 (-17 to -24 %); shots on target 4.6 per team were right in absolute terms but 44 % of shots, against about 34 % in the league. → Recalibrated: shot rate ×1.35, xG per shot ×0.86, saves 35 % → 25 % of non-goal shots. Shots 13.2, on target 4.5 | `test_match_distribution_is_premier_league_like[shots_per_team, sot_per_team]` |

## Realism of the match distribution

Reference: all 380 matches of each of 2023-24, 2024-25 and 2025-26 in the [football-data.co.uk](https://www.football-data.co.uk/englandm.php) `E0.csv` files (result, shots, shots on target), computed per season; the range is across the three seasons. `docs/DATA.md` already cited goals; the other columns are new. Simulator: seeds 0-99.

| Per match | Reference (3 seasons) | Simulator before | Simulator after |
| --- | --- | --- | --- |
| Goals | 2.75 - 3.28 | 2.73 | 2.92 |
| Share of 0-0 | 2.9 - 7.1 % | 3 % | 4 % |
| Share of 6+ goals | 4.2 - 9.5 % | 6 % | 4 % |
| Home win / draw / away win | 41-46 % / 22-27 % / 30-35 % | 48 / 23 / 29 % | 47 / 17 / 36 % |
| Shots per team | 12.5 - 13.8 | 10.4 | 13.2 |
| Shots on target per team | 4.2 - 4.9 | 4.6 | 4.5 |
| Matches won by 4+ goals | 2 - 9 % | 7 % | 3 % |
| Passes, both teams (Opta 2024-25: 893) | 893 | 932 | 908 |
| Accurate passes per team (about 360) | 360 | 365 | 356 |

Outliers: seed 42 ended 1-5 before the change. A four-goal margin is ordinary (2-9 % of league matches), so that result was a tail event, not a bug; after the recalibration the stream changed and seed 42 ends 2-2. The draw share (17 %) is the one value below the league range; with 100 matches it is within about 1.5 standard errors, and the test allows it.

The recalibration was kept because `python -m whyitmatters.eval --seeds 20 --check`, the realism tests and the Truth Score tests (1.00) stay green. Detection moved from precision 0.67 / recall 0.87 / timeline accuracy 0.82 to 0.66 / 0.91 / 0.82.

## Reproduce

```bash
pytest tests/test_stats_audit.py
```

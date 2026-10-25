# Data sheet

## Why the data is synthetic

The hackathon's [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) (section 4.7) say that no match footage or data is distributed to participants, and that projects must use synthetic, football-realistic data. WhyItMatters therefore generates its own matches with a seeded simulator (`src/whyitmatters/simulator/`). Every club, player and match is fictional. The same seed always produces the same match.

## File format

A match is one JSONL file with one record per line: a `meta` line first, then one `event` line per action, then a `truth` line last. The line-per-event layout lets the same file be replayed as a live stream.

```bash
python -m whyitmatters.simulator --seed 7 --out match.jsonl
```

### `meta`

The match id, seed, venue and kick-off time, plus both teams, each with an id, name, short name, side, formation and 11 players (`id`, `name`, `number`, `position`, `side`).

### `event`

| Field | Type | Meaning |
| --- | --- | --- |
| `id`, `seq` | string, int | unique id and order in the match |
| `t`, `period`, `minute` | float, 1 or 2, int | match seconds from kick-off (monotonic across both halves) |
| `type` | string | `kick_off`, `pass`, `carry`, `shot`, `pressure`, `tackle`, `interception`, `foul`, `ball_out`, `half_end` |
| `side`, `player_id` | `home`/`away`, string | the acting team and player |
| `possession_id` | int | increases with every new possession |
| `x`, `y` | metres | where it happened, in the **acting team's** coordinates |
| `end_x`, `end_y` | metres | where a pass, carry or shot ended |
| `outcome` | string | `complete`/`incomplete` (pass), `goal`/`saved`/`off_target`/`blocked` (shot), `won`/`lost` (tackle, interception) |
| `receiver_id` | string | receiver of a completed pass |
| `under_pressure` | bool | the actor was pressed |
| `pass_distance`, `pass_difficulty` | metres, 0-1 | pass length and how hard it was (distance, pressure, target zone) |
| `ball_speed_kmh` | km/h | pass, carry or shot speed |
| `xg` | 0-1 | expected goals of a shot |
| `score_home`, `score_away` | int | score after the event |
| `freeze` | object | positions of all 22 players (below) |

Real example lines from seed 7 (`freeze` omitted for space):

```json
{"id": "syn-0007-wha-hbc-00002", "t": 1.0, "minute": 0, "type": "pass", "side": "away", "player_id": "hbc-10", "possession_id": 2, "x": 48.0, "y": 34.0, "end_x": 50.8, "end_y": 42.1, "outcome": "complete", "receiver_id": "hbc-6", "under_pressure": false, "pass_distance": 8.6, "pass_difficulty": 0.28, "ball_speed_kmh": 40.5}
{"id": "syn-0007-wha-hbc-00009", "t": 27.0, "minute": 0, "type": "carry", "side": "home", "player_id": "wha-7", "x": 41.5, "y": 13.7, "end_x": 42.0, "end_y": 11.1, "ball_speed_kmh": 16.0}
{"id": "syn-0007-wha-hbc-00006", "t": 18.5, "minute": 0, "type": "pressure", "side": "away", "player_id": "hbc-9", "x": 77.1, "y": 48.3}
{"id": "syn-0007-wha-hbc-00005", "t": 17.7, "minute": 0, "type": "interception", "side": "home", "player_id": "wha-4", "x": 27.9, "y": 19.7, "outcome": "won"}
{"id": "syn-0007-wha-hbc-00032", "t": 98.8, "minute": 1, "type": "tackle", "side": "away", "player_id": "hbc-3", "x": 1.0, "y": 14.1, "outcome": "won"}
{"id": "syn-0007-wha-hbc-00630", "t": 2135.9, "minute": 35, "type": "foul", "side": "away", "player_id": "hbc-5", "x": 28.0, "y": 1.0}
{"id": "syn-0007-wha-hbc-00034", "t": 107.1, "minute": 1, "type": "ball_out", "side": "away", "x": 18.9, "y": 22.7}
{"id": "syn-0007-wha-hbc-00149", "t": 476.9, "minute": 7, "type": "shot", "side": "home", "player_id": "wha-9", "x": 97.8, "y": 55.7, "end_x": 105.0, "end_y": 32.8, "outcome": "saved", "ball_speed_kmh": 104.1, "xg": 0.041}
```

### `freeze` (positions of all 22 players)

Every on-ball event carries a freeze frame, in the style of StatsBomb 360 data. `t` holds the acting team's 11 players and `o` the opponents, each in its team's `players` order, all in the acting team's coordinates:

```json
"freeze": {"t": [[3.9, 32.9], [18.3, 55.3], "... 11 pairs"], "o": [[102.7, 34.4], [53.8, 15.1], "... 11 pairs"]}
```

How they are generated is described in [METHODS.md](METHODS.md#freeze-frames).

### `truth`

These are the known answers the simulator planted. The agents never see them; they are used only for evaluation.

- `phases`: who was scripted to control the game, and when (`home_control`, `away_control`, `chaos`, `balanced`).
- `key_moments`: goals and big chances (xG ≥ 0.3), each pointing to its event id.
- `shapes`: per phase and team, the shape in and out of possession and the block, for example `{"side": "home", "start_minute": 0.0, "end_minute": 12.9, "in_possession": "4-3-3", "out_of_possession": "4-4-2", "block": "mid"}`.

## Coordinates and clock

- The pitch is 105 × 68 m. Every team attacks left to right in its own coordinates (x = 0 is its own goal line, x = 105 the opponent's), so the same zone means the same thing for both teams.
- To place an away event on a shared picture, mirror it: (105 − x, 68 − y).
- The first half runs from 0 to 45:00 with no added time. The second half runs from 45:00 to 90:00 plus 1 to 5 minutes, so `t` never resets.

## Calibration against real league averages

The simulator's averages over seeds 0-99, compared with public Premier League figures:

| Per match | Simulator (seeds 0-99) | Reference | Gap | Source |
| --- | --- | --- | --- | --- |
| Passes, both teams | 931.5 | 893.4 (2024-25) | +4 % | [Opta Analyst](https://theanalyst.com/articles/premier-league-teams-still-more-direct-2025-26) |
| Long balls ≥ 32 m, both teams | 94.0 | 93.4 (2024-25) | +1 % | same article |
| Goals | 2.73 | ≈ 2.80 (2025-26; derived: 587 goals in 210 games) | −3 % | same article |
| Accurate passes per team | 364.8 | ≈ 360.5 (2025-26; derived: mean of the 20 teams) | +1 % | [playerstats.football](https://playerstats.football/premier-league/stats/accurate-passes/previous) |
| Shots, both teams | 20.9 | not used: no source checked yet | — | — |

"Derived" means we computed the reference from the source's own numbers; the source does not state it as a single figure.

The simulator was recalibrated to this table: more long balls in build-up, a slightly slower tempo and slightly better chance quality. After recalibrating, every evaluation was re-run and is still above its CI target; the current numbers are in the [README](../README.md#measured-not-claimed).

Reproduce the table with:

```bash
python -c "import statistics as s; from whyitmatters.simulator import simulate; ms=[simulate(i) for i in range(100)]; print(s.mean(sum(e.type=='pass' for e in m.events) for m in ms))"
```

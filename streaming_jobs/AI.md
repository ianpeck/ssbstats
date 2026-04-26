# AI.md — Streaming Pipeline Internals

This file is a self-contained briefing for an AI model that needs to extend or
debug the local-only Kafka + Flink + SSE pipeline that powers the **Gamecast**
page. For broader app context (DB conventions, prod deployment, repo layout)
see [`/CLAUDE.md`](../CLAUDE.md).

If you change the architecture, **update this file** so the next model has
accurate context.

---

## What this pipeline does

Replays historical Smash Bros matches from the production MySQL DB as
**synthesized per-tick telemetry**, processes the telemetry through Flink, and
renders an ESPN-style live "Gamecast" page in Flask.

- **Final outcomes are real** — winner + exact final stock count come from the DB.
- **Per-tick details are synthesized** — positions, damage %, actions, KO timing
  are all fabricated to match a believable shape converging on the real result.
- **Production-safe** — every new component lives behind `LOCAL_STREAMING=1`
  and reads the DB read-only. With the flag off, zero new routes register and
  the prod deploy is identical to before.

---

## High-level architecture

```
[Flask /gamecast/start]                                            [Flask /gamecast]
        │                                                                  ▲
        │ POST                                                             │ SSE
        ▼                                                                  │
   [picker]──► match.scheduled ──► [synthesizer service] ──► match.telemetry
                                                                  │
                              ┌───────────────────────────────────┼───────────────────┐
                              ▼                                   ▼                   ▼
                  [Flink: live_state]            [Flink: win_probability]   [Flink: notable_events]
                              │                                   │                   │
                              ▼                                   ▼                   ▼
                       match.live_state                   match.win_prob        match.events
                              │                                   │                   │
                              └───────────────────────────────────┴───────────────────┘
                                                       ▼
                                      Flask SSE multiplexes all three to browser
```

5 Kafka topics (all keyed by `match_id`):

| Topic | Producer | Consumer(s) |
|-------|----------|-------------|
| `match.scheduled` | picker | synthesizer service |
| `match.telemetry` | synthesizer | all Flink jobs |
| `match.live_state` | Flink `live_state.py` | Flask SSE |
| `match.win_prob` | Flink `win_probability.py` | (currently unused — page does ELO blend client-side) |
| `match.events` | Flink `notable_events.py` | Flask SSE |

Topic names live in [`kafka_io.py`](kafka_io.py). Default bootstrap server
`localhost:9094` (host) / `kafka:9092` (inside compose network).

---

## File map

```
streaming_jobs/
├── AI.md                            # this file
├── README.md                        # human-facing run instructions
├── requirements.txt                 # PyYAML + confluent-kafka
├── kafka_io.py                      # topic constants + producer/consumer factories
├── config/
│   └── fighter_physics.yaml         # per-fighter Smash Ultimate weights + KO curve
├── picker/
│   └── main.py                      # reads FightLog, emits match.scheduled
├── synthesizer/
│   ├── config.py                    # YAML loader → FighterPhysics dataclass
│   ├── model.py                     # FighterState, hit/KO probability, action picker
│   ├── match.py                     # MatchConfig, StockTarget, run_match (the simulator)
│   ├── sinks.py                     # StdoutSink, JsonlSink, KafkaSink
│   ├── main.py                      # CLI: synthesize one match standalone
│   └── service.py                   # daemon: consume match.scheduled → produce telemetry
└── flink/
    ├── README.md
    ├── requirements.txt             # PyFlink only — install separately
    ├── download_jars.sh             # fetches flink-sql-connector-kafka into lib/
    ├── lib/                         # connector JARs (mounted into Flink containers)
    └── jobs/
        ├── _common.py               # KAFKA_BOOTSTRAP, JAR registration helper
        ├── live_state.py            # latest-tick passthrough via upsert-kafka
        ├── win_probability.py       # logistic on stock_diff + damage_diff
        └── notable_events.py        # clutch_ko / speed_kill SQL pattern detection

ssbstats_app/streaming/
├── __init__.py
└── gamecast.py                      # Flask blueprint, only registered if LOCAL_STREAMING=1

templates/gamecast.html              # extends base.html, has stage SVG, damage/stock cards, ticker
static/js/pages/gamecast.js          # EventSource consumer, stage rendering, SD banner

docker-compose.local.yml             # Kafka (KRaft, no ZK) + Kafka UI + Flink JM + TM
```

---

## Critical domain knowledge

### `Match_Result` column — the constraint source of truth

The synthesizer pins simulations to the historical outcome by reading the
`Match_Result` column on `Results` / `FightLog`. **Interpretation depends on
fight type.** This is the single most important thing to get right.

**Stock-format matches** (`Description` IN `'1 stock'`, `'3 stock'`, `'5 stock'`):
- Winner's `Match_Result` > 0 → **stocks remaining at end of match**.
  - Example: 3-stock fight, winner row has `Match_Result = 2` → final score "3-1"
    (loser's 3 stocks all KO'd, winner had 2 left).
- Winner's `Match_Result` = 0 → **sudden death win** (see below).
- Loser's `Match_Result` is mostly 0. Negative values exist for losers but the
  picker ignores them — loser always ends at 0 stocks.

**Timed-format matches** (`'1 minute'`, `'3 minute'`, `'5 minute'`, `Coin`, etc.):
- `Match_Result` is a running net `(KOs_landed - deaths)` per fighter.
  Each KO landed = +1, each death = -1. Final value at timeout = net.
- **Currently NOT supported by the synthesizer.** Picker filters them out via
  the `STOCK_FIGHT_TYPES` whitelist in [`picker/main.py`](picker/main.py).

**Other fight types** (Tournament, Royal Rumble, Tag Team, Cash In, Scramble,
Money in the Bank, Smash Series, Stamina, Pokeball, Special, Handicap):
- Various conventions, mostly 0/1 for participation. Excluded from the picker.

### Sudden death (SD)

SD happens when both fighters are KO'd on their last stock simultaneously.
DB representation: winner's `Match_Result == 0`. SD is a separate phase, not
just a normal match where the winner happened to end at 0 stocks.

**Synthesizer's SD sequence:**
1. Normal play until both fighters reduced to 1 stock each.
2. Force a "double KO" event — both stocks drop to 0 simultaneously
   (`last_event = "double_ko"`, both `stocks = 0`).
3. SD setup: both fighters reset to **1 stock at exactly 300% damage**, recentered
   on stage (`last_event = "sudden_death_start"`, `phase = "sudden_death"`).
4. Continue normal action loop. Winner is hard-protected from any KO. Loser
   takes the next clean KO. **No respawn happens in SD** (loser hits 0 stocks
   and the existing `if defender.stocks > 0: reset_after_ko()` guard skips).
5. Emit `match_over`.

The `phase` field on `TickEvent` flips from `"normal"` to `"sudden_death"`
permanently at step 3 — UI uses this to flash the red banner.

### Fighter name normalization (DB ⇄ physics YAML ⇄ assets)

Fighter names in the DB use these specific spellings (NOT the obvious ones):

- `DK` (not "Donkey Kong")
- `Mr Game & Watch` (no period after `Mr`)
- `Banjo & Kazooie` (with the ampersand surrounded by spaces)
- `Erdrick` (this is the Smash slot for "Hero")
- `Pokemon Trainer` (single entry — DB does not split into Squirtle/Ivysaur/Charizard)
- `Richter Belmont`, `Simon Belmont` (full names)
- `ROB` (no periods — note the `Elo` table and `FightLog` both use this; the
  earlier doc-style `R.O.B.` would silently never match)

These are the canonical forms in [`fighter_physics.yaml`](config/fighter_physics.yaml)
and must match the DB's `Fighter_Name` exactly. The picker's filter clause
`fw.Fighter_Name IN (...)` cross-references this list.

For asset filenames (PNG paths), there's separate normalization in
[`ssbstats_app/utils.py`](../ssbstats_app/utils.py) (`fighter_to_filename` /
`stage_to_filename`). The streaming pipeline does not use those directly —
it just passes the raw DB name through to the browser.

### Multi-fighter matches are excluded

The picker filters to fights with exactly 2 `FightLog` rows (one W, one L).
3-way and free-for-all matches (e.g. Fight #1200) are excluded entirely. The
synthesizer's data model assumes 1v1 throughout.

---

## The simulator (`synthesizer/match.py`) in detail

### Data model

```python
@dataclass(frozen=True)
class StockTarget:
    total_stocks: int            # 1, 3, or 5 (from fight type)
    winner_stocks_remaining: int # 1..total_stocks; for SD this is 1 (the SD stock)
    is_sudden_death: bool

    @classmethod
    def from_match_result(cls, total_stocks, winner_match_result):
        # winner_match_result == 0 → sudden death; else → stocks remaining
```

```python
@dataclass
class MatchConfig:
    match_id: str
    fighter_a: FighterPhysics    # winner is whichever name matches winner_name
    fighter_b: FighterPhysics
    winner_name: str
    target: StockTarget
    tick_rate_hz: float = 10.0
    seed: int | None = None
```

### Simulation loop (`run_match`)

Tick rate default 10 Hz. Each tick:

1. **SD trigger check** (only if `is_sudden_death=True`, both at 1 stock, not yet
   in SD phase): emit `double_ko`, reset both to 1 stock @ 300%, set `sd_phase=True`,
   emit `sudden_death_start`.
2. **Pick actions** for both fighters (`idle / move / attack / dodge / recover`,
   weighted in [`model.py:random_action`](synthesizer/model.py)).
3. **Resolve attacks** (each fighter attacking is independent):
   - Compute `hit_probability` (proximity, defender dodge state, attacker cooldown,
     plus `attacker_bias`).
   - On hit: defender damage increases by `random_damage` (2–25 from YAML range).
   - Compute `ko_probability` (logistic on damage, scaled by `100/weight`).
   - On KO: apply safeguards (next section).
4. **Emit `TickEvent`** with current state and any event tag.
5. End check: `loser.stocks == 0` → emit `match_over`, return.
6. Hard cap: 15 minutes. On hit, force `loser.stocks = 0` and emit `match_over`.

### Constraint safeguards (the heart of "outcome-exact" simulation)

These two rules guarantee the simulation hits the historical final score
**exactly**, no more no less:

- **In normal phase, when defender is the winner:**
  Skip the KO if `winner_deaths >= winner_normal_deaths`. (Winner has already
  taken their full quota of deaths.)
- **In normal phase, when defender is the loser AND on their final stock:**
  - If non-SD match: skip until `winner_deaths >= winner_normal_deaths`.
  - If SD match: skip until `winner.stocks == 1` (so both reach 1 simultaneously).
- **In SD phase:** Skip every KO attempt where defender is the winner. Loser
  KO ends the match.

Where:
- `winner_normal_deaths = total_stocks - winner_stocks_remaining` for normal,
  `total_stocks - 1` for SD (both end normal play at 1 stock).
- `loser_normal_deaths = total_stocks` for normal (loser ends at 0),
  `total_stocks - 1` for SD (loser still has the SD stock to lose).

### Adaptive bias

A small bias (+0.10 to `hit_probability`) is given each tick to whichever
attacker is "behind" on target deaths. This prevents stalls without making the
winner feel artificially dominant:

```python
winner_remaining = winner_normal_deaths - winner_deaths
loser_remaining  = loser_normal_deaths - loser_deaths
if loser_remaining > winner_remaining:
    biased_attacker = winner   # need more loser KOs
elif winner_remaining > loser_remaining:
    biased_attacker = loser    # need more winner KOs
else:
    biased_attacker = winner   # tie → slight winner default

# In SD phase: always winner.
```

### Pacing knobs (tune carefully)

Realistic match duration target: **1.5–4 minutes for 3-stock**, **3–5 minutes
for 5-stock**. Validated empirically across 100+ random matches.

| Knob | File | Current | Effect |
|------|------|---------|--------|
| `ko_curve.threshold` | `config/fighter_physics.yaml` | 170 | Higher → more damage needed before KO is likely → slower matches |
| `ko_curve.steepness` | `config/fighter_physics.yaml` | 0.04 | Lower → more lingering at high % |
| `damage_range` | `config/fighter_physics.yaml` | [2, 25] | Bigger range = more variance per hit |
| Fighter `weight` | `config/fighter_physics.yaml` | 62–135 | KO chance scales by `100 / weight`. Real Smash Ultimate values. |
| `hit_probability` base | `synthesizer/model.py` | 0.18 | Lower → more whiffs → slower |
| Action weights | `synthesizer/model.py` | attack=0.15 | Lower attack weight → fewer hit attempts per tick |
| `base_bias` | `synthesizer/match.py` | 0.10 | Adaptive bias magnitude |
| `tick_rate_hz` | `synthesizer/match.py` | 10 | Telemetry frequency |

If you change pacing knobs, re-run the smoke test in CLAUDE memory or:

```bash
python -c "
from streaming_jobs.synthesizer.config import load_physics
from streaming_jobs.synthesizer.match import MatchConfig, StockTarget, run_match
from pathlib import Path
import statistics
physics = load_physics(Path('streaming_jobs/config/fighter_physics.yaml'))
def run(fa, fb, ts, wmr, seed):
    cfg = MatchConfig('t', physics[fa], physics[fb], fa, StockTarget.from_match_result(ts, wmr), seed=seed)
    last = None
    for ev in run_match(cfg): last = ev
    return last.elapsed_sec
durs = [run('Mario','Pichu',3,1,s) for s in range(50)]
print(f'mean={statistics.mean(durs)/60:.1f}min median={statistics.median(durs)/60:.1f}min')
"
```

---

## Kafka layer (`kafka_io.py`)

- Uses **confluent-kafka** Python client (industry standard, prebuilt Windows
  wheels — no librdkafka build required).
- Topic constants exported as `TOPIC_SCHEDULED`, `TOPIC_TELEMETRY`,
  `TOPIC_LIVE_STATE`, `TOPIC_WIN_PROB`, `TOPIC_EVENTS`.
- `make_producer()` — `lz4` compression, `linger.ms=10`, JSON values, string keys.
- `make_consumer(group_id, topics, from_latest=False)` — set `from_latest=True`
  for SSE streams so each browser tab sees current matches not history.
- `ensure_topics()` — idempotent CreateTopics call. Synthesizer service runs
  this on boot. Bitnami Kafka has auto-create on by default, so this is belt-and-suspenders.
- `produce_json(producer, topic, key, value)` — JSON-serialize, encode key as
  UTF-8, send, then `producer.poll(0)` to serve delivery callbacks.

`KafkaSink` in [`sinks.py`](synthesizer/sinks.py) wraps a producer and emits
each `TickEvent` keyed by `match_id` for partition affinity.

---

## Flink jobs (`flink/jobs/`)

All three jobs use **PyFlink Table API** with SQL DDL — keeps the code legible
and avoids most of the PyFlink Java-bridge rough edges. Each job:

1. Creates a `TableEnvironment` in streaming mode.
2. Registers `flink-sql-connector-kafka` JAR via `_common.add_kafka_connector_jar`.
3. Declares Kafka source + sink tables with explicit JSON schemas.
4. Runs an `INSERT INTO ... SELECT ...` that's a continuous job.

Submit via:
```bash
docker compose -f docker-compose.local.yml exec flink-jobmanager \
    flink run -py /opt/flink/jobs/<job>.py
```

(Compose mounts `streaming_jobs/flink/jobs/` into `/opt/flink/jobs/` and
`streaming_jobs/flink/lib/` into `/opt/flink/usrlib/`.)

### `live_state.py`
- Source: `match.telemetry` (Kafka)
- Sink: `match.live_state` (upsert-kafka, primary key `match_id`)
- Logic: pure pass-through. The upsert-kafka connector automatically keeps only
  the latest row per key, which is exactly what the Gamecast UI wants — "current
  state of match X" without reading every raw tick.

### `win_probability.py`
- Source: `match.telemetry`
- Sink: `match.win_prob` (upsert-kafka)
- Logic: SQL logistic on `stock_diff` and `damage_diff`:
  ```
  p_a = 1 / (1 + exp(-(0.8 * stock_diff + 0.015 * (b_damage - a_damage))))
  ```

### `notable_events.py`
- Source: `match.telemetry`
- Sink: `match.events` (regular Kafka, append-only)
- Logic: SQL pattern detection via two `INSERT INTO` statements in a `StatementSet`:
  - `clutch_ko`: `event = 'ko'` AND `MAX(damage) >= 150`
  - `speed_kill`: `event = 'ko'` AND `tick < 20`
- More CEP patterns (comeback after being down 2 stocks, etc.) are easy to add
  but require the DataStream CEP API rather than SQL — currently a TODO.

### Telemetry schema (used by all 3 jobs)

```sql
CREATE TABLE telemetry (
    match_id STRING,
    tick INT,
    elapsed_sec DOUBLE,
    phase STRING,
    fighters ARRAY<ROW<name STRING, x DOUBLE, y DOUBLE, damage DOUBLE, stocks INT, action STRING>>,
    event STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'match.telemetry',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-<job>',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json'
)
```

Note `phase` was added after the initial schema — Flink's JSON connector
ignores unknown fields and treats missing ones as NULL, so adding fields is
backwards-compatible. **Removing** fields is not.

---

## Flask integration (`ssbstats_app/streaming/gamecast.py`)

### Conditional registration

In [`ssbstats_app/__init__.py`](../ssbstats_app/__init__.py):

```python
if os.getenv("LOCAL_STREAMING", "0") == "1":
    from ssbstats_app.streaming.gamecast import gamecast_bp
    app.register_blueprint(gamecast_bp)
```

Also a context processor exposes `streaming_enabled` to templates so the navbar
in [`base.html`](../templates/base.html) only shows the Gamecast link locally.

### Three endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/gamecast` | Render page |
| POST   | `/gamecast/start` | Pick historical match → publish `match.scheduled` → return match metadata as JSON |
| GET    | `/gamecast/stream` | Server-Sent Events: forwards `match.live_state`, `match.win_prob`, `match.events` to browser as named events |

### SSE design

Each `/gamecast/stream` request creates:
1. A bounded `queue.Queue(maxsize=1000)` for handoff
2. A daemon thread (`kafka_pump`) that polls a fresh consumer (unique
   `group.id` per request, `from_latest=True`) and pushes onto the queue
3. A generator (`sse_generator`) that drains the queue and yields SSE-formatted
   text (`event: <name>\ndata: <json>\n\n`)

**Backpressure**: if the browser is slow, `out_q.put_nowait()` raises `queue.Full`
and the message is **dropped** rather than blocking the producer thread. Acceptable
for live data — fresh state arrives momentarily.

**Cleanup**: the generator's `finally` sets a `threading.Event` that the pump
thread checks each loop. Consumer is closed there too.

### Frontend (`gamecast.js`) — ESPN gamecast layout

EventSource API consumes two of the three named event types:
- `live_state` → updates fighter portraits, damage, stocks, clock, phase banner,
  per-stock damage history, win probability chart
- `event` → prepends to "Notable Events" ticker
- `win_prob` (from Flink) → **currently ignored** — the page computes its own
  blended win probability client-side using ELO (see below)

Layout: matchup header with fighter portraits and ELO ratings, big
stocks/damage cards, **ELO-blended win probability line chart** (Chart.js,
already loaded by base.html), per-stock damage history per fighter, and the
notable-events ticker. No stage diagram — the synthesizer's x/y coordinates are
not used in the UI.

#### Win probability — ELO baseline blended with live state

The picker includes ELO snapshots from the `Elo` table (`elo_before`/`elo_after`
for each fighter at the picked fight). The page computes win probability as:

```
elo_prior  = 1 / (1 + 10^((opp_elo - my_elo) / 400))           # standard ELO formula
state_prob = logistic(0.6 * stock_diff + 0.005 * -damage_diff) # current-state estimate
weight     = 0.15 + (stocks_consumed / total_stocks_at_risk) * 0.77
final      = (1 - weight) * elo_prior + weight * state_prob
```

So:
- **Match start**: weight ≈ 0.15 → ELO dominates. The line opens at the prior.
- **Mid-match**: weight ≈ 0.55 → blend of both.
- **End of match**: weight ≈ 0.92 → state dominates. Wherever the stocks are
  going, the line follows.

This produces the right narrative: an underdog winning early shifts the line
slightly, but a 2-0 lead late in a 3-stock match basically pins the line to
their color regardless of the ELO delta.

The Flink `win_probability.py` job still runs and emits to `match.win_prob` —
it's the "raw state-only" probability and could be displayed as a secondary
trace later. Currently the SSE handler ignores it.

#### Stock-loss tracking

Per-tick, the JS captures the **previous tick's** damage when stocks decrease.
This matters because the synthesizer respawns on KO and resets damage to 0 in
the same tick, so reading damage from the "stocks dropped" tick gives 0.
Captured into `stockHistA` / `stockHistB` and rendered as "Stock N — at M:SS — XX%".

#### Stock-loss banner

On any stock decrease, a fixed-position banner slides in: `<NAME> — STOCK
LOST @ XX%`. Auto-dismisses after 1.8s.

#### Sudden death

Same red SUDDEN DEATH banner as before, persists during the SD phase. The
`double_ko` event flashes the page; `match_over` updates the top pill to show
the final score.

#### Fighter portraits

Loaded from `/static/assets/fighters/<fighter_to_filename>.png`. The JS reimplements
[`utils.fighter_to_filename`](../ssbstats_app/utils.py) inline (lowercase, strip
spaces/dots, `&`→`and`, plus the `banjo & kazooie`→`banjoandkazooie` override).
On 404 the image goes semi-transparent.

---

## How to run end-to-end

```bash
# One-time: fetch the Flink connector JAR
bash streaming_jobs/flink/download_jars.sh

# Bring up Kafka + Flink
docker compose -f docker-compose.local.yml up -d

# Submit Flink jobs (continuous, run once)
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/live_state.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/win_probability.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/notable_events.py &

# Synthesizer service (consumes match.scheduled, produces telemetry)
python -m streaming_jobs.synthesizer.service --realtime

# Flask app with streaming enabled
LOCAL_STREAMING=1 python app.py

# Browser
# http://localhost:5001/gamecast → click "Start a Match"
```

UIs: Kafka UI on `:8080`, Flink Web UI on `:8081`.

### Standalone synthesizer (no Kafka required)

For tuning the simulator without bringing up the stack:

```bash
python -m streaming_jobs.synthesizer.main "Mario" "Pichu" "Mario" \
    --total-stocks 3 --winner-stocks-remaining 1 --seed 42
```

---

## Common gotchas

- **`fighter_physics.yaml` names must exactly match DB `Fighter_Name`.** If you
  add a new fighter to the DB, add an entry here too with their Smash Ultimate
  weight, or the picker will silently exclude any fight involving them.
- **The Flink connector JAR is NOT in the repo.** Run `download_jars.sh` first.
  Without it, `pipeline.jars` resolves to no files and Flink job submission
  fails with a connector-not-found error.
- **PyFlink jobs are submitted to the dockerized cluster, not run locally.** PyFlink
  installation in your local venv is optional — only needed if you want to run
  jobs in `LocalStreamEnvironment` mode.
- **Fight #1200 is a 3-fighter free-for-all** — the picker correctly excludes it
  via the `HAVING COUNT(*) = 2` clause. If you ever loosen that filter, the
  synthesizer will break (its model assumes exactly 2 fighters).
- **`Match_Result` for losers is unreliable** — see schema notes above. Always
  read the **winner's** row to determine final score.
- **The DB has no per-stock damage, no time-to-KO, no real positional data.**
  Everything visual past "two dots and a damage number" is invented. Be honest
  about this in any UI text.
- **The picker uses `ORDER BY RAND() LIMIT 1`** — fine for ~10K rows, would be
  slow on millions. Don't copy this pattern into prod paths.
- **SSE generators don't release Kafka consumers if the client disconnects
  abruptly.** The cleanup is in the generator's `finally`, which Python *should*
  invoke when the response generator is GC'd. If you see consumer-group bloat
  in Kafka UI, that's why.
- **Bitnami Kafka with KRaft mode** (no ZooKeeper) is what we use. If you
  swap images, double-check the env vars — Bitnami's are very different from
  Confluent's.
- **The synthesizer's tick is purely random** — no notion of stage hazards,
  combos, recovery situations, projectiles. Adding any of these is a deeper
  rewrite, not a tweak.

---

## Extension points

If you're asked to extend this pipeline, here are the cleanest seams:

1. **Timed-format matches (1/3/5 minute, Coin)**: Add `TimedTarget` in
   [`match.py`](synthesizer/match.py). Picker needs to encode `duration_sec`,
   `winner_net_kills`, `loser_net_kills`. Simulator needs a wall-clock cap and
   bias schedule that hits the net-kills target as time approaches 0.

2. **Multi-fighter matches**: Larger refactor. `FighterState` collection becomes
   a list, every iteration loop becomes O(n²) for attack pairs, safeguards need
   per-fighter death tracking. Picker filter can loosen, but the visual layout
   needs more than 2 stage dots.

3. **Per-stock active Pokémon for Pokemon Trainer**: Currently treated as a
   single fighter (weight 96, the Ivysaur middle-ground). Could rotate
   active Pokémon per stock by giving `FighterPhysics` an optional `stock_overrides`
   list and reading them on KO/respawn.

4. **More CEP patterns** (comeback, zero-to-death, edge-guard): SQL is too
   limited — switch to PyFlink DataStream CEP API in a new job. Keep the Kafka
   topic the same so the SSE consumer doesn't need to change.

5. **Real stage layouts**: Stage names from `Location_Name` in `FightLog`. Could
   map to per-stage geometry (platforms, blast zones) via a new YAML similar to
   `fighter_physics.yaml`. Stage geometry would constrain `STAGE_LEFT/RIGHT/FLOOR/CEILING`
   in [`model.py`](synthesizer/model.py).

6. **In-process Flink (no docker for Flink)**: Replace `flink run` submission
   with `LocalStreamEnvironment` inside a Python thread spawned from the Flask
   app's startup. Kafka would still need docker. The compose file's Flink
   containers can stay around as the "production-style deployment" path.

7. **Replay buffering**: Currently `from_latest=True` on the SSE consumer means
   late-joining browser tabs miss the start of a match. To fix, either add a
   small Redis ring buffer, or change to `from_earliest` with a per-tab seek
   (more complex; not worth it for an MVP).

---

## Things to NOT do

- **Never INSERT/UPDATE/DELETE the prod DB.** This is in [`/CLAUDE.md`](../CLAUDE.md)
  but bears repeating: the picker is the only DB consumer in this pipeline and
  it must remain read-only.
- **Don't add new top-level routes outside the `LOCAL_STREAMING` gate.** Anything
  that ships to EB has prod consequences.
- **Don't import `streaming_jobs.*` at module-import time inside `ssbstats_app/`
  except inside the gated `if os.getenv("LOCAL_STREAMING") == "1":` block.**
  Otherwise you create a hard dependency on `confluent_kafka` for prod.
- **Don't change the Kafka topic names or message schemas without updating ALL
  consumers** (synthesizer service, all 3 Flink jobs, Flask SSE pump). The
  topics are the contract; breaking it silently breaks the demo.
- **Don't try to make the synthesizer "more realistic" by giving the loser
  more bias when they're losing.** The adaptive bias already handles fairness;
  any further tinkering risks breaking outcome-correctness.

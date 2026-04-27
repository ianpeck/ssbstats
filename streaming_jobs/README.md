# streaming_jobs

Local-only Kafka + Flink pipeline that powers the `/gamecast` page. Nothing in
this directory ships to Elastic Beanstalk. The Flask routes only exist when you
start the app with `LOCAL_STREAMING=1`.

## Plain-English Summary

This folder turns one historical Smash match into a live-looking broadcast.

The database only tells us the real matchup, winner, and final stock count. The
streaming stack invents the second-by-second action in a way that still lands on
that real final result.

The short version:

1. Flask picks a historical match.
2. Kafka carries that match request to the simulator.
3. The simulator emits fake live telemetry about 10 times per second.
4. Flink continuously reads that telemetry and creates cleaner output streams.
5. Flask reads those output streams and forwards them to the browser with SSE.
6. The Gamecast page updates live.

## Kafka And Flink In One Minute

Kafka is the message bus. In this repo, think of it like named inboxes called
topics. Code can publish JSON messages to a topic, and other code can subscribe
to that topic. The producer and consumer do not have to run in the same process.

Flink is the stream processor. In this repo, Flink jobs run forever. They read
Kafka topics as if they were tables, apply SQL, and write new rows back to Kafka.
Instead of "run a query and finish", these jobs keep reacting as new messages
arrive.

So Kafka moves events around. Flink transforms those events while they are still
moving.

## The Pipeline

```text
Browser clicks "Start a Match"
        |
        v
Flask POST /gamecast/start
        |
        | picks one real historical match from the DB
        v
Kafka topic: match.scheduled
        |
        | consumed by the synthesizer service
        v
Synthesizer service
        |
        | emits one simulated match tick at a time
        v
Kafka topic: match.telemetry
        |
        +------------------------+--------------------------+
        |                        |                          |
        v                        v                          v
Flink live_state.py      Flink win_probability.py   Flink notable_events.py
        |                        |                          |
        v                        v                          v
match.live_state         match.win_prob             match.events
        |                        |                          |
        +------------------------+--------------------------+
                                 |
                                 v
Flask GET /gamecast/stream consumes Kafka and sends Server-Sent Events
                                 |
                                 v
Browser updates the Gamecast UI
```

## Topics

All Kafka topic names live in `streaming_jobs/kafka_io.py`.

| Topic | Written by | Read by | What it means |
| --- | --- | --- | --- |
| `match.scheduled` | Flask picker | Synthesizer service | "Replay this historical match." |
| `match.telemetry` | Synthesizer service | All Flink jobs | Raw per-tick simulated match state. |
| `match.live_state` | Flink `live_state.py` | Flask SSE stream | Latest visible state for each match. |
| `match.win_prob` | Flink `win_probability.py` | Flask SSE stream | Raw state-only win probability. The current page mostly computes its own ELO-blended chart. |
| `match.events` | Flink `notable_events.py` | Flask SSE stream | Append-only notable moments, such as high-damage KOs. |

Messages are keyed by `match_id`. That keeps all messages for one match grouped
under the same Kafka key and lets the upsert topics replace the old value with
the newest value for that match.

## What Each Piece Does

### Flask `/gamecast/start`

When you click "Start a Match", the browser calls `POST /gamecast/start`.
That endpoint:

1. uses the picker to read one eligible historical 1v1 stock match from the DB;
2. returns the match metadata to the browser;
3. publishes the same metadata to Kafka topic `match.scheduled`.

This is the request that starts the whole stream.

### Synthesizer service

The synthesizer is a long-running Python process:

```bash
python -m streaming_jobs.synthesizer.service --realtime --tick-rate 10
```

It waits for messages on `match.scheduled`. For each scheduled match, it runs the
simulator and publishes many JSON tick events to `match.telemetry`.

A telemetry event is the raw live feed. It includes fields like:

```text
match_id, tick, elapsed_sec, phase, fighters, event
```

The `fighters` field contains each fighter's name, position, damage, stock count,
and current action. These per-tick details are synthesized, but the winner and
final stock count are constrained to match the real DB result.

### Flink jobs

The Flink jobs live in `streaming_jobs/flink/jobs/`. Each one declares Kafka
topics as SQL tables, then runs a continuous `INSERT INTO ... SELECT ...`.

`live_state.py`

Reads every raw tick from `match.telemetry` and writes it to `match.live_state`
using `upsert-kafka`. "Upsert" means Kafka keeps the newest row per `match_id`.
That is perfect for the UI because the page usually wants "what is the match
state right now?", not the entire tick history.

`win_probability.py`

Reads `match.telemetry`, compares stocks and damage, and writes a simple
probability estimate to `match.win_prob`.

`notable_events.py`

Reads `match.telemetry`, filters for interesting moments, and writes event rows
to `match.events`. Current examples are high-damage KOs and very early KOs.

Important: the Flink source tables use `latest-offset`, so start the Flink jobs
before clicking "Start a Match". If the match already streamed past, a newly
started Flink job may skip those older messages.

### Flask `/gamecast/stream`

The browser opens `GET /gamecast/stream` with the EventSource API. Flask creates
a Kafka consumer for:

```text
match.live_state
match.win_prob
match.events
```

Then Flask forwards those Kafka messages to the browser as Server-Sent Events:

```text
live_state -> updates damage, stocks, clock, phase, and match display
event      -> prepends a notable moment to the ticker
win_prob   -> available from Flink, though the current JS mostly uses its own chart logic
```

That means the browser does not talk to Kafka directly. Flask is the bridge
between Kafka and the page.

## Talk Track

Use this when you need to explain the project out loud:

"The Gamecast demo is local-only. When I click Start, Flask picks a real match
from the database and publishes a `match.scheduled` message to Kafka. A Python
synthesizer consumes that message and generates live-looking telemetry ticks,
then publishes those ticks to `match.telemetry`. Flink runs continuous SQL jobs
over that telemetry. One job keeps the latest match state, one calculates a raw
win probability, and one extracts notable events. Those outputs go back into
Kafka. Flask consumes the Flink output topics and streams them to the browser
with Server-Sent Events, so the UI updates like a live broadcast."

## One-Time Setup

```bash
# Install Python deps for picker + synthesizer + Kafka client
pip install -r streaming_jobs/requirements.txt

# Optional: install PyFlink only if you want to run jobs locally too
pip install -r streaming_jobs/flink/requirements.txt

# Download the Flink-Kafka SQL connector JAR
bash streaming_jobs/flink/download_jars.sh

# Bring up Kafka + Flink containers
docker compose -f docker-compose.local.yml up -d
```

Local UIs:

| UI | URL | Use it for |
| --- | --- | --- |
| Kafka UI | http://localhost:8080 | Inspect topics and messages. |
| Flink Web UI | http://localhost:8081 | Check whether Flink jobs are running. |

## Running The Pipeline

Open one terminal for the synthesizer, one for Flask, and submit the Flink jobs
from a shell that supports backgrounding with `&` such as Git Bash. If you are
using PowerShell, run the three Flink commands in separate terminals.

```bash
# Terminal 1: synthesizer service
python -m streaming_jobs.synthesizer.service --realtime --tick-rate 10

# Terminal 2: submit Flink jobs once; they keep running
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/live_state.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/win_probability.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/notable_events.py &

# Terminal 3: Flask app with local streaming enabled, PowerShell
$env:LOCAL_STREAMING="1"
python app.py

# Bash/Git Bash equivalent:
# LOCAL_STREAMING=1 python app.py
```

Then open:

```text
http://localhost:5001/gamecast
```

Click "Start a Match". The picker publishes `match.scheduled`, the synthesizer
publishes `match.telemetry`, Flink publishes processed topics, and the browser
updates from Flask's SSE stream.

## Quick Debug Checklist

If the page does not move:

1. Make sure Docker compose is running Kafka and Flink.
2. Make sure the synthesizer service is running before you click Start.
3. Make sure all three Flink jobs were submitted before you click Start.
4. Check Kafka UI for messages in `match.scheduled` and `match.telemetry`.
5. Check Flink UI for running jobs.
6. Make sure Flask was started with `LOCAL_STREAMING=1`.

## Standalone Synthesizer

For quick simulator testing without Kafka or Flink:

```bash
python -m streaming_jobs.synthesizer.main "Bowser" "Pichu" "Bowser" --total-stocks 3 --winner-stocks-remaining 1 --seed 42 --tick-rate 5
```

## Tuning

- `config/fighter_physics.yaml`: per-fighter weight, damage range, and KO curve
- `synthesizer/match.py`: convergence schedule, sudden-death handling, KO rules
- `synthesizer/model.py`: action choices, hit probability, KO probability, normal damage caps

## Roadmap

- [x] Synthesizer with winner-convergence
- [x] Kafka producer sink
- [x] Match picker with read-only DB query
- [x] Docker compose Kafka + Flink
- [x] PyFlink jobs: live state, win probability, notable events
- [x] Flask `/gamecast` page + SSE endpoint, gated on `LOCAL_STREAMING=1`
- [x] Weight-sensitive normal-phase damage cap
- [ ] CEP comeback detection
- [ ] Smoother early-game pacing
- [ ] Per-stock active Pokemon for Pokemon Trainer

## Common Streaming Pitfalls

The five problems that show up over and over in real Kafka + Flink systems,
explained with this project's data so they're concrete. Each one has a fix or
prevention pattern that's worth internalizing before scaling a pipeline.

### 1. Late events land in the wrong time window (event time vs ingestion time)

**The scenario.** The fight engine publishes `match.telemetry` at 10 Hz. A
match starts at 8:00:00 PM. Tick 1 at 8:00:00.0, tick 2 at 8:00:00.1, and so on.
A brief network blip causes the engine to buffer locally for 30 seconds, then at
8:00:30 it floods Kafka with all 300 buffered ticks at once.

**What breaks.** A Flink job computing "damage taken per 5-second tumbling
window" using Kafka's broker timestamp sees all 300 ticks as having arrived at
8:00:30. Result: a giant fake damage spike at 8:00:30, and the windows for
8:00:00 through 8:00:30 look completely empty. Every windowed metric is wrong.

**The fix.** The producer stamps each message with an `emitted_at` field
recording when the event actually happened. Flink uses event-time semantics
with watermarks pointed at `emitted_at` instead of broker time. Now Flink
routes each tick to the window it really belongs to, and watermarks tell the
job "messages may arrive a few seconds late, hold each window open until the
watermark passes."

**Prevention.** Add `emitted_at` from day one on every producer, even if you
think you don't need event-time processing yet. It's a near-free field at
write time and impossible to backfill correctly later. Pair it with a
documented watermark policy ("we tolerate up to 30 seconds of lateness") so
operators know what late-arrival behavior to expect.

### 2. Backfills compress time and break every windowed job

**The scenario.** You change the win-probability formula and want to recompute
the last six months of fights with the new logic. You replay the whole season
back into `match.telemetry` over an hour.

**What breaks.** Six months of events arrive in one hour. Tumbling-window jobs
think every event happened "right now." Stateful aggregations explode.
Watermarks jump backwards and forwards chaotically. Live consumers fall behind
their SLAs because the broker is firehosing them historical data they don't
care about. Even worse: Kafka retention is finite (default 7 days). The data
isn't even in Kafka anymore for most of those 6 months.

**The fix.** Don't backfill from Kafka. Continuously archive every Kafka
topic to a lakehouse (Iceberg or Delta on S3) the moment messages arrive.
The lakehouse becomes your replay source of truth. When you need to backfill,
spin up a separate Flink job in **batch mode** that reads bounded data from
Iceberg, writes to a separate output topic or table, and then atomically swap
consumers over to the new view. Kafka retention stays short and cheap; the
lakehouse holds history forever for cents per GB.

**Prevention.** Every Kafka topic should have a continuous archive job from
day one — a single Flink Iceberg sink per topic costs almost nothing to run.
Combined with `emitted_at` from issue #1, this gives you "rebuild any derived
state from any point in history with corrected logic" as a routine operation
rather than a panic.

### 3. Schema drift silently breaks consumers

**The scenario.** The fight-engine team adds a `stage_hazards` field to
`match.telemetry`. A month later they decide to rename `damage` to
`damage_pct` because it's more accurate. They deploy on a Friday afternoon.

**What breaks.** The Gamecast Flask consumer is parsing `data["damage"]`. The
moment the new producer ships, every `KeyError` lights up in prod. The
notable-events Flink job's SQL `WHERE GREATEST(fighters[1].damage, ...)`
returns NULLs forever because the field name no longer exists. Nobody noticed
because the producer team didn't have visibility into which consumers depended
on `damage`.

**The fix at runtime.** Roll the producer back. There is no good runtime fix
for this. The consumers are broken until either the producer reverts or every
consumer is updated. This is the pain that schema discipline exists to prevent.

**The prevention.** Use **Avro or Protobuf with Schema Registry** instead of
raw JSON. Every `match.telemetry` message carries a 5-byte prefix pointing to
its schema version. Producers register the schema with the registry before
publishing; consumers fetch it by ID and decode. The registry enforces
**compatibility rules at registration time**: with `BACKWARD` compatibility,
the registry rejects a schema that removes or renames a field, so the
breaking change never reaches Kafka. Producer team sees a registration error
in their CI, fixes it, prod stays healthy.

In this repo we use plain JSON for simplicity (one developer, one repo).
Avro + Schema Registry becomes load-bearing the moment producers and
consumers are owned by different teams.

### 4. Duplicate messages from at-least-once delivery

**The scenario.** The fight engine publishes a `ko` event for Mario losing
his second stock. The Kafka broker actually committed the write, but the ACK
to the producer got dropped mid-flight. The producer retries. Now the same
KO event sits in `match.events` twice. A Flink aggregation computing "stocks
remaining per fighter" subtracts 2 instead of 1. The standings page shows
Mario in a 3-stock fight at 4-3 instead of 3-2.

**What breaks.** Quietly, in ways nobody notices until an analyst asks "why
did this fight have 7 stock changes in a 3-stock match?". By then, every
downstream system that consumed those events has already incorporated the
duplicate. ELO recalculations are wrong. Standings are wrong. The lakehouse
archive has the dupes too.

**The fix at the Kafka layer.** Modern Kafka clients have
`enable.idempotence=true` by default (Kafka 3.0+), which de-duplicates retries
**within a producer session**. Combined with the transactional API, you get
"exactly-once" semantics inside Kafka.

**The fix end-to-end.** Even with idempotent producers, your consumers must
be idempotent because crashes between read and act can still cause duplicate
processing. Three patterns:

- **Stable record IDs as Kafka keys.** Use the natural ID of the event
  (`ko_event_id`, `fight_id + tick`) as the message key. Sinks like
  `upsert-kafka`, Snowflake `MERGE`, or Postgres `INSERT ON CONFLICT` then
  treat the second arrival as a no-op.
- **Idempotent operations.** "Set `current_stocks = 2`" is idempotent;
  "decrement `current_stocks` by 1" is not. Design write-paths to be the
  former wherever possible.
- **Dedup tables.** For non-upsert sinks, maintain a small "seen event IDs"
  table and skip if the ID is already present.

**Prevention.** Bake the assumption "duplicates can always happen" into
every consumer's design. Don't trust Kafka's exactly-once guarantee
end-to-end — it's only end-to-end if every consumer is idempotent too.

### 5. Late-joining viewers miss the start of the match

**The scenario.** Mario vs Pichu has been streaming for 90 seconds. Mario is
already up 3-1. A new viewer opens the Gamecast page. Their browser opens
an SSE connection to `/gamecast/stream`, which subscribes to Kafka with
`from_latest=True`.

**What breaks.** The new viewer sees the next tick that arrives — but they
have no idea what the score is, what stage it's on, or what happened in the
previous 90 seconds. The page shows "0:00 — Stocks ●●● ●●●" until the next
KO redraws everything. Confusing and obviously broken.

**The fix.** **Snapshot-then-stream.** When a viewer connects:

1. Read the latest snapshot from `match.live_state` (an `upsert-kafka` topic
   that holds only the most recent tick per `match_id`). Push that to the
   viewer immediately so they see "the current state" in one round trip.
2. Then subscribe to `match.live_state` and `match.events` and forward
   incremental updates as they arrive.

This is exactly the pattern this repo uses with the `live_state.py` Flink
job — `upsert-kafka` semantics keep "latest snapshot per match" available
for cheap point reads, while the same topic supports continuous streaming
for incremental updates.

**Prevention.** Every realtime UI should support both reads. The "snapshot"
read makes the page useful on first load; the "stream" subscription keeps
it live. Designing UIs as stream-only causes exactly this class of bug.
The Flink upsert-kafka pattern is the canonical way to give yourself both
reads from the same logical stream.

---

The shared theme across all five: **Kafka by itself doesn't solve any of
these.** Kafka is a durable ordered log of bytes. The fixes live one layer
up — in producer discipline (`emitted_at`, schemas, keys), in stream
processor design (event-time, watermarks, idempotency), and in storage
choices (lakehouse for replay, upsert-kafka for snapshots). A "production"
streaming system is mostly just Kafka surrounded by consistent answers to
these five problems.

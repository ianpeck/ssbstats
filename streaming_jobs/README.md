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

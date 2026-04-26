# streaming_jobs

Local-only Kafka + Flink pipeline that powers the `/gamecast` page. **Nothing
in this directory ships to Elastic Beanstalk.** Activated by `LOCAL_STREAMING=1`.

## Architecture

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
                                            (Flask SSE multiplexes all three)
```

## One-time setup

```bash
# Install Python deps for picker + synthesizer + Kafka client
pip install -r streaming_jobs/requirements.txt

# (Optional) Install PyFlink only if you want to run jobs locally too
pip install -r streaming_jobs/flink/requirements.txt

# Download the Flink-Kafka SQL connector JAR
bash streaming_jobs/flink/download_jars.sh

# Bring up Kafka + Flink containers
docker compose -f docker-compose.local.yml up -d
```

UIs:
- Kafka topics & messages: http://localhost:8080
- Flink Web UI: http://localhost:8081

## Running the pipeline

Open three terminals, plus one Flask:

```bash
# Terminal 1 — Synthesizer service (consumes match.scheduled, emits telemetry)
python -m streaming_jobs.synthesizer.service --realtime --tick-rate 10

# Terminal 2 — Submit Flink jobs (one-time, they run continuously)
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/live_state.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/win_probability.py &
docker compose -f docker-compose.local.yml exec flink-jobmanager flink run -py /opt/flink/jobs/notable_events.py &

# Terminal 3 — Flask app with streaming enabled
LOCAL_STREAMING=1 python app.py

# Then in your browser:
#   http://localhost:5001/gamecast
#   click "Start a Match" → picker reads a real historical fight, publishes it,
#   the synthesizer produces telemetry, Flink processes, the page updates live.
```

## Standalone synthesizer (no Kafka required)

For quick simulator testing without bringing up the stack:

```bash
python -m streaming_jobs.synthesizer.main "Bowser" "Pichu" "Bowser" --duration 60 --seed 42 --tick-rate 5
```

## Tuning

- `config/fighter_physics.yaml` — per-fighter weight (KO sensitivity), damage range, stocks
- `synthesizer/match.py` — convergence schedule (`winner_bias` ramp), KO probabilities

## Roadmap

- [x] Synthesizer with winner-convergence
- [x] Kafka producer sink
- [x] Match picker (read-only DB query)
- [x] docker-compose Kafka + Flink
- [x] PyFlink jobs: live state, win probability, notable events (clutch KO, speed kill)
- [x] Flask `/gamecast` page + SSE endpoint, gated on `LOCAL_STREAMING=1`
- [ ] CEP comeback detection (was down ≥2 stocks → wins)
- [ ] Damage cap + smoother early-game pacing
- [ ] Per-stock active Pokemon for Pokemon Trainer

# Flink jobs

PyFlink jobs that consume `match.telemetry` and emit downstream topics that the
Flask `/gamecast` page renders.

## One-time setup

```bash
# 1. Pull the Kafka SQL connector JAR (one-time, lands in ./lib)
bash streaming_jobs/flink/download_jars.sh

# 2. Bring up the local stack
docker compose -f docker-compose.local.yml up -d
```

Web UIs:
- Flink: http://localhost:8081
- Kafka UI: http://localhost:8080

## Submitting a job

The compose file mounts `./jobs` into `/opt/flink/jobs` inside the JobManager
container, so you can submit by referring to the path inside the container:

```bash
docker compose -f docker-compose.local.yml exec flink-jobmanager \
    flink run -py /opt/flink/jobs/live_state.py

docker compose -f docker-compose.local.yml exec flink-jobmanager \
    flink run -py /opt/flink/jobs/win_probability.py

docker compose -f docker-compose.local.yml exec flink-jobmanager \
    flink run -py /opt/flink/jobs/notable_events.py
```

Each job runs continuously. Cancel from the Flink UI or with `flink cancel`.

## Output topics

| Topic | Schema (key by match_id) | Producer |
|-------|--------------------------|----------|
| `match.live_state` | latest tick snapshot | `live_state.py` |
| `match.win_prob`   | per-tick win probability | `win_probability.py` |
| `match.events`     | one row per notable moment | `notable_events.py` |

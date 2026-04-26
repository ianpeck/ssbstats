"""Live state job.

Reads `match.telemetry`, keys by match_id, and republishes the latest snapshot
on `match.live_state`. The Gamecast page consumes this topic so it always sees
the most recent tick per match without having to read every raw telemetry event.

Submit:
  docker compose -f docker-compose.local.yml exec flink-jobmanager \
      flink run -py /opt/flink/jobs/live_state.py
"""
from __future__ import annotations

from pyflink.table import EnvironmentSettings, TableEnvironment

from _common import KAFKA_BOOTSTRAP, add_kafka_connector_jar


def main() -> None:
    settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(settings)
    add_kafka_connector_jar(t_env)

    t_env.execute_sql(f"""
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
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'properties.group.id' = 'flink-live-state',
            'scan.startup.mode' = 'latest-offset',
            'format' = 'json'
        )
    """)

    t_env.execute_sql(f"""
        CREATE TABLE live_state (
            match_id STRING,
            tick INT,
            elapsed_sec DOUBLE,
            phase STRING,
            fighters ARRAY<ROW<name STRING, x DOUBLE, y DOUBLE, damage DOUBLE, stocks INT, action STRING>>,
            event STRING,
            PRIMARY KEY (match_id) NOT ENFORCED
        ) WITH (
            'connector' = 'upsert-kafka',
            'topic' = 'match.live_state',
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'key.format' = 'json',
            'value.format' = 'json'
        )
    """)

    # upsert-kafka keeps only the latest row per key — exactly what we want for
    # "current state of match X". No window or retraction logic needed.
    t_env.execute_sql("""
        INSERT INTO live_state
        SELECT match_id, tick, elapsed_sec, phase, fighters, event
        FROM telemetry
    """).wait()


if __name__ == "__main__":
    main()

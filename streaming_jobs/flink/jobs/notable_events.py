"""Notable events job.

Detects interesting moments inside a match and emits one row per moment to
`match.events`. Patterns covered (kept SQL-only for clarity):

- KO at high damage: defender was at >= 150% when KO'd  -> "clutch_ko"
- Speed kill: KO landed before tick 20                  -> "speed_kill"
- Double KO: both fighters KO'd simultaneously          -> "double_ko"
- Sudden death triggered                                -> "sudden_death"
- Match over (final score)                              -> "match_over"

(Stateful CEP patterns like "comeback after being down 2 stocks" are easier to
add later with the DataStream CEP API once the simple stuff is stable.)

Submit:
  docker compose -f docker-compose.local.yml exec flink-jobmanager \
      flink run -py /opt/flink/jobs/notable_events.py
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
            'properties.group.id' = 'flink-notable',
            'scan.startup.mode' = 'latest-offset',
            'format' = 'json'
        )
    """)

    t_env.execute_sql(f"""
        CREATE TABLE events (
            match_id STRING,
            tick INT,
            elapsed_sec DOUBLE,
            kind STRING,
            note STRING
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'match.events',
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'format' = 'json'
        )
    """)

    # KO at high damage on either fighter
    clutch_ko = """
        INSERT INTO events
        SELECT
            match_id, tick, elapsed_sec,
            'clutch_ko' AS kind,
            CONCAT('KO at ',
                   CAST(CAST(GREATEST(fighters[1].damage, fighters[2].damage) AS INT) AS STRING),
                   '% damage') AS note
        FROM telemetry
        WHERE event = 'ko'
          AND GREATEST(fighters[1].damage, fighters[2].damage) >= 150
    """

    # KO landed in the opening seconds
    speed_kill = """
        INSERT INTO events
        SELECT
            match_id, tick, elapsed_sec,
            'speed_kill' AS kind,
            'Stock taken in the opening seconds' AS note
        FROM telemetry
        WHERE event = 'ko' AND tick < 20
    """

    # Both fighters KO'd on the same tick - the synthesizer fires this only
    # when an SD-flagged match reaches its mandated double-KO moment.
    double_ko = """
        INSERT INTO events
        SELECT
            match_id, tick, elapsed_sec,
            'double_ko' AS kind,
            'Both fighters KO''d simultaneously' AS note
        FROM telemetry
        WHERE event = 'double_ko'
    """

    # SD phase begins - both fighters at 1 stock @ 300%, single KO decides it.
    sudden_death = """
        INSERT INTO events
        SELECT
            match_id, tick, elapsed_sec,
            'sudden_death' AS kind,
            'Sudden death - one stock, 300%, winner takes all' AS note
        FROM telemetry
        WHERE event = 'sudden_death_start'
    """

    # Match over - final score in the note for the ticker.
    match_over = """
        INSERT INTO events
        SELECT
            match_id, tick, elapsed_sec,
            'match_over' AS kind,
            CONCAT(
                'Final: ',
                fighters[1].name, ' ', CAST(fighters[1].stocks AS STRING),
                ' - ',
                CAST(fighters[2].stocks AS STRING), ' ', fighters[2].name
            ) AS note
        FROM telemetry
        WHERE event = 'match_over'
    """

    stmt_set = t_env.create_statement_set()
    stmt_set.add_insert_sql(clutch_ko)
    stmt_set.add_insert_sql(speed_kill)
    stmt_set.add_insert_sql(double_ko)
    stmt_set.add_insert_sql(sudden_death)
    stmt_set.add_insert_sql(match_over)
    stmt_set.execute().wait()


if __name__ == "__main__":
    main()

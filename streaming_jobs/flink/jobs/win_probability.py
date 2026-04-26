"""Win probability job.

Computes a simple logistic estimate of P(fighter_a wins) from each telemetry tick:
    logit = 0.8 * stock_diff + 0.015 * (b_damage - a_damage)
    p_a   = 1 / (1 + exp(-logit))

Stock differential dominates; damage is the secondary signal. Output topic is
keyed by match_id so the Gamecast page can subscribe to a single match.

Submit:
  docker compose -f docker-compose.local.yml exec flink-jobmanager \
      flink run -py /opt/flink/jobs/win_probability.py
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
            'properties.group.id' = 'flink-win-prob',
            'scan.startup.mode' = 'latest-offset',
            'format' = 'json'
        )
    """)

    t_env.execute_sql(f"""
        CREATE TABLE win_prob (
            match_id STRING,
            tick INT,
            fighter_a STRING,
            fighter_b STRING,
            p_a DOUBLE,
            p_b DOUBLE,
            stock_diff INT,
            damage_diff DOUBLE,
            PRIMARY KEY (match_id) NOT ENFORCED
        ) WITH (
            'connector' = 'upsert-kafka',
            'topic' = 'match.win_prob',
            'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
            'key.format' = 'json',
            'value.format' = 'json'
        )
    """)

    # Logistic in pure SQL: 1 / (1 + exp(-logit))
    t_env.execute_sql("""
        INSERT INTO win_prob
        SELECT
            match_id,
            tick,
            fighters[1].name AS fighter_a,
            fighters[2].name AS fighter_b,
            1.0 / (1.0 + EXP(-(0.8 * (fighters[1].stocks - fighters[2].stocks)
                              + 0.015 * (fighters[2].damage - fighters[1].damage)))) AS p_a,
            1.0 - 1.0 / (1.0 + EXP(-(0.8 * (fighters[1].stocks - fighters[2].stocks)
                                   + 0.015 * (fighters[2].damage - fighters[1].damage)))) AS p_b,
            fighters[1].stocks - fighters[2].stocks AS stock_diff,
            fighters[1].damage - fighters[2].damage AS damage_diff
        FROM telemetry
    """).wait()


if __name__ == "__main__":
    main()

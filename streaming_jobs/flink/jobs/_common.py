"""Shared helpers for the PyFlink jobs.

Each job follows the same shape:
  1. create a streaming TableEnvironment
  2. register Kafka source + sink tables
  3. run a SQL transformation between them

Inside the Flink containers, Kafka is reachable as kafka:9092.
Outside (running PyFlink locally), it's localhost:9094.
"""
from __future__ import annotations

import os
from pathlib import Path


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")


def add_kafka_connector_jar(table_env) -> None:
    """Tell PyFlink where to find the Kafka SQL connector JAR.

    When the job runs inside the Flink container, the JAR is at
    /opt/flink/usrlib (mounted from streaming_jobs/flink/lib).
    """
    jar_dir = Path(os.getenv("FLINK_JAR_DIR", "/opt/flink/usrlib"))
    if not jar_dir.is_dir():
        # local dev: try the repo path
        jar_dir = Path(__file__).resolve().parents[1] / "lib"
    jars = list(jar_dir.glob("flink-sql-connector-kafka-*.jar"))
    if not jars:
        raise RuntimeError(
            f"No flink-sql-connector-kafka JAR found in {jar_dir}. "
            f"Run streaming_jobs/flink/download_jars.sh first."
        )
    uris = ";".join(f"file://{jar}" for jar in jars)
    table_env.get_config().set("pipeline.jars", uris)

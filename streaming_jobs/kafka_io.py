"""Shared Kafka client helpers for the local streaming stack.

All topics in this project follow the `match.*` naming convention. Only used
when the local Kafka cluster (docker-compose.local.yml) is running.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


# Topic names — kept here so producers and consumers stay aligned.
TOPIC_SCHEDULED = "match.scheduled"     # picker -> synthesizer
TOPIC_TELEMETRY = "match.telemetry"     # synthesizer -> Flink
TOPIC_LIVE_STATE = "match.live_state"   # Flink -> app
TOPIC_WIN_PROB = "match.win_prob"       # Flink -> app
TOPIC_EVENTS = "match.events"           # Flink -> app

ALL_TOPICS = (TOPIC_SCHEDULED, TOPIC_TELEMETRY, TOPIC_LIVE_STATE, TOPIC_WIN_PROB, TOPIC_EVENTS)


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str

    @classmethod
    def from_env(cls) -> "KafkaConfig":
        return cls(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "localhost:9094"))


def make_producer(cfg: KafkaConfig | None = None):
    """Return a confluent_kafka.Producer wired to the local cluster."""
    from confluent_kafka import Producer  # imported lazily so non-Kafka code paths don't need the dep

    cfg = cfg or KafkaConfig.from_env()
    return Producer({
        "bootstrap.servers": cfg.bootstrap_servers,
        "linger.ms": 10,
        "compression.type": "lz4",
    })


def make_consumer(group_id: str, topics: list[str], from_latest: bool = False, cfg: KafkaConfig | None = None):
    """Return a confluent_kafka.Consumer subscribed to the given topics."""
    from confluent_kafka import Consumer

    cfg = cfg or KafkaConfig.from_env()
    consumer = Consumer({
        "bootstrap.servers": cfg.bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": "latest" if from_latest else "earliest",
        "enable.auto.commit": True,
    })
    consumer.subscribe(topics)
    return consumer


def produce_json(producer, topic: str, key: str, value: dict) -> None:
    """Publish a JSON-serialized event with a string key."""
    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=json.dumps(value).encode("utf-8"),
    )
    producer.poll(0)  # serve delivery callbacks


def ensure_topics(cfg: KafkaConfig | None = None, num_partitions: int = 1, replication: int = 1) -> None:
    """Idempotently create the project topics. Safe to call on every startup."""
    from confluent_kafka.admin import AdminClient, NewTopic

    cfg = cfg or KafkaConfig.from_env()
    admin = AdminClient({"bootstrap.servers": cfg.bootstrap_servers})
    existing = set(admin.list_topics(timeout=5).topics.keys())
    to_create = [
        NewTopic(t, num_partitions=num_partitions, replication_factor=replication)
        for t in ALL_TOPICS
        if t not in existing
    ]
    if not to_create:
        return
    futures = admin.create_topics(to_create)
    for topic, fut in futures.items():
        try:
            fut.result()
        except Exception as exc:  # noqa: BLE001
            # Race with auto-create — fine to ignore "already exists" errors.
            if "already exists" not in str(exc).lower():
                raise

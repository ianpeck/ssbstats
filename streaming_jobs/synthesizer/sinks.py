from __future__ import annotations

import json
from typing import Protocol, TextIO

from .match import TickEvent


class Sink(Protocol):
    def emit(self, event: TickEvent) -> None: ...
    def close(self) -> None: ...


class StdoutSink:
    def emit(self, event: TickEvent) -> None:
        print(json.dumps(event.to_dict()))

    def close(self) -> None:
        pass


class JsonlSink:
    def __init__(self, path: str) -> None:
        self._fp: TextIO = open(path, "w", encoding="utf-8")

    def emit(self, event: TickEvent) -> None:
        self._fp.write(json.dumps(event.to_dict()) + "\n")

    def close(self) -> None:
        self._fp.close()


class KafkaSink:
    """Publish each tick to a Kafka topic, keyed by match_id for partition affinity."""

    def __init__(self, topic: str, producer=None) -> None:
        from streaming_jobs.kafka_io import make_producer
        self._topic = topic
        self._producer = producer or make_producer()

    def emit(self, event: TickEvent) -> None:
        from streaming_jobs.kafka_io import produce_json
        produce_json(self._producer, self._topic, key=event.match_id, value=event.to_dict())

    def close(self) -> None:
        self._producer.flush(5)

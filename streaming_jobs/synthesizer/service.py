"""Long-running synthesizer service.

Consumes match.scheduled, runs the simulator, and publishes every tick to
match.telemetry. Run alongside the picker + Flink + Flask app to get a fully
streaming pipeline.

Usage:
    python -m streaming_jobs.synthesizer.service
"""
from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

from streaming_jobs.kafka_io import TOPIC_SCHEDULED, TOPIC_TELEMETRY, ensure_topics, make_consumer
from streaming_jobs.synthesizer.config import load_physics
from streaming_jobs.synthesizer.match import MatchConfig, StockTarget, run_match
from streaming_jobs.synthesizer.sinks import KafkaSink


PHYSICS_PATH = Path(__file__).resolve().parents[1] / "config" / "fighter_physics.yaml"


_should_stop = False


def _on_signal(_signum, _frame):
    global _should_stop
    _should_stop = True
    print("Shutting down synthesizer service...", file=sys.stderr)


def _build_target(match: dict) -> StockTarget:
    """Reconstruct a StockTarget from the picker's published payload."""
    return StockTarget(
        total_stocks=int(match["total_stocks"]),
        winner_stocks_remaining=int(match["winner_stocks_remaining"]),
        is_sudden_death=bool(match.get("is_sudden_death", False)),
    )


def _simulate(match: dict, physics: dict, sink: KafkaSink, tick_rate_hz: float, realtime: bool) -> None:
    target = _build_target(match)
    cfg = MatchConfig(
        match_id=match["match_id"],
        fighter_a=physics[match["fighter_a"]],
        fighter_b=physics[match["fighter_b"]],
        winner_name=match["winner"],
        target=target,
        tick_rate_hz=tick_rate_hz,
        seed=match.get("seed"),
    )
    period = 1.0 / tick_rate_hz
    score = "SUDDEN DEATH" if target.is_sudden_death else f"{target.total_stocks}-{target.total_stocks - target.winner_stocks_remaining}"
    print(f"[{cfg.match_id}] simulating {cfg.fighter_a.name} vs {cfg.fighter_b.name} "
          f"(winner={cfg.winner_name}, {score})", file=sys.stderr)
    for ev in run_match(cfg):
        sink.emit(ev)
        if realtime:
            time.sleep(period)
    print(f"[{cfg.match_id}] done", file=sys.stderr)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Synthesizer service: consume match.scheduled, produce match.telemetry")
    parser.add_argument("--tick-rate", type=float, default=10.0)
    parser.add_argument("--realtime", action="store_true", default=True,
                        help="Sleep between ticks so the stream is paced like a real broadcast")
    parser.add_argument("--no-realtime", dest="realtime", action="store_false")
    parser.add_argument("--group-id", default="synthesizer-service")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    ensure_topics()
    physics = load_physics(PHYSICS_PATH)
    consumer = make_consumer(group_id=args.group_id, topics=[TOPIC_SCHEDULED])
    sink = KafkaSink(topic=TOPIC_TELEMETRY)

    print(f"Synthesizer listening on {TOPIC_SCHEDULED}, emitting to {TOPIC_TELEMETRY}", file=sys.stderr)
    try:
        while not _should_stop:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"Kafka error: {msg.error()}", file=sys.stderr)
                continue
            try:
                match = json.loads(msg.value().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"Bad message dropped: {exc}", file=sys.stderr)
                continue

            for fname in (match.get("fighter_a"), match.get("fighter_b"), match.get("winner")):
                if fname not in physics:
                    print(f"Skipping match — unknown fighter {fname!r}", file=sys.stderr)
                    break
            else:
                _simulate(match, physics, sink, args.tick_rate, args.realtime)
    finally:
        consumer.close()
        sink.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

from .config import load_physics
from .match import MatchConfig, StockTarget, run_match
from .sinks import JsonlSink, KafkaSink, StdoutSink


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "fighter_physics.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize a Smash Bros match telemetry stream that converges on a known final score."
    )
    parser.add_argument("fighter_a", help="Name of fighter A (must match DB Fighter_Name)")
    parser.add_argument("fighter_b", help="Name of fighter B (must match DB Fighter_Name)")
    parser.add_argument("winner", help="Historical winner — must equal fighter_a or fighter_b")
    parser.add_argument("--total-stocks", type=int, default=3, help="1, 3, or 5")
    parser.add_argument(
        "--winner-stocks-remaining",
        type=int,
        default=1,
        help="Stocks the winner ended with (1..total). Pass 0 for sudden death.",
    )
    parser.add_argument("--tick-rate", type=float, default=10.0, help="Telemetry tick rate (Hz)")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    parser.add_argument("--realtime", action="store_true", help="Sleep between ticks to emit at real time")
    parser.add_argument("--sink", choices=["stdout", "jsonl", "kafka"], default="stdout")
    parser.add_argument("--out", default="match.jsonl", help="Output path for jsonl sink")
    parser.add_argument("--topic", default="match.telemetry", help="Topic for kafka sink")
    args = parser.parse_args()

    physics = load_physics(CONFIG_PATH)
    for n in (args.fighter_a, args.fighter_b, args.winner):
        if n not in physics:
            raise SystemExit(
                f"Unknown fighter: {n!r}. Available: {sorted(physics)[:5]}... (see {CONFIG_PATH.name})"
            )

    target = StockTarget.from_match_result(
        total_stocks=args.total_stocks,
        winner_match_result=args.winner_stocks_remaining,
    )

    cfg = MatchConfig(
        match_id=str(uuid.uuid4())[:8],
        fighter_a=physics[args.fighter_a],
        fighter_b=physics[args.fighter_b],
        winner_name=args.winner,
        target=target,
        tick_rate_hz=args.tick_rate,
        seed=args.seed,
    )

    if args.sink == "kafka":
        sink = KafkaSink(topic=args.topic)
    elif args.sink == "jsonl":
        sink = JsonlSink(args.out)
    else:
        sink = StdoutSink()

    period = 1.0 / args.tick_rate
    try:
        for ev in run_match(cfg):
            sink.emit(ev)
            if args.realtime:
                time.sleep(period)
    finally:
        sink.close()


if __name__ == "__main__":
    main()

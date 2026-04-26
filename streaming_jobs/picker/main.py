"""Pick a real historical singles fight from the SmashBros DB and publish it.

Output modes:
- stdout   — print one JSON line, useful for piping into the synthesizer
- kafka    — publish to the `match.scheduled` topic (synthesizer service consumes it)

Strictly read-only against the prod DB. Filters to **stock-format singles only**
(1/3/5 stock, exactly 2 fighters, both in fighter_physics.yaml). Multi-fighter
matches and time-format matches are excluded for now.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

# Reuse the existing app's read-only DB helper so we share connection config
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ssbstats_app.repositories.base import select_view_dicts  # noqa: E402

from streaming_jobs.kafka_io import TOPIC_SCHEDULED, make_producer, produce_json  # noqa: E402
from streaming_jobs.synthesizer.config import load_physics  # noqa: E402


PHYSICS_PATH = Path(__file__).resolve().parents[1] / "config" / "fighter_physics.yaml"

# Stock-format fight types we currently know how to simulate.
STOCK_FIGHT_TYPES = {
    "1 stock": 1,
    "3 stock": 3,
    "5 stock": 5,
}


def _supported_fighters() -> set[str]:
    return set(load_physics(PHYSICS_PATH).keys())


def pick_match(season: int | None = None, ppv: str | None = None) -> dict:
    """Pick a random stock-format singles fight and return its essential fields.

    Filters:
      - exactly two FightLog rows (true 1v1)
      - one W and one L
      - both fighters in fighter_physics.yaml
      - Description in {1 stock, 3 stock, 5 stock}
    """
    supported = _supported_fighters()
    fighter_placeholders = ", ".join(["%s"] * len(supported))
    type_placeholders = ", ".join(["%s"] * len(STOCK_FIGHT_TYPES))

    where = [
        "fw.Fighter_Name IN (" + fighter_placeholders + ")",
        "fl.Fighter_Name IN (" + fighter_placeholders + ")",
        "fw.Description IN (" + type_placeholders + ")",
    ]
    params: list = list(supported) + list(supported) + list(STOCK_FIGHT_TYPES.keys())

    if season is not None:
        where.append("fw.Season = %s")
        params.append(season)
    if ppv:
        where.append("fw.PPV_Name = %s")
        params.append(ppv)

    sql = f"""
        SELECT
            fw.Fight_ID          AS fight_id,
            fw.Season            AS season,
            fw.Month             AS month,
            fw.Week              AS week,
            fw.PPV_Name          AS ppv,
            fw.Location_Name     AS stage,
            fw.Championship_Name AS championship,
            fw.Description       AS fight_type,
            fw.Fighter_Name      AS winner,
            fl.Fighter_Name      AS loser,
            fw.Match_Result      AS winner_match_result,
            ROUND(ew.elo_before, 1) AS winner_elo_before,
            ROUND(ew.elo_after, 1)  AS winner_elo_after,
            ROUND(el.elo_before, 1) AS loser_elo_before,
            ROUND(el.elo_after, 1)  AS loser_elo_after
        FROM FightLog fw
        JOIN FightLog fl ON fw.Fight_ID = fl.Fight_ID AND fl.Decision = 'L'
        LEFT JOIN Elo ew  ON ew.result_id = fw.Result_ID
        LEFT JOIN Elo el  ON el.result_id = fl.Result_ID
        JOIN (
            SELECT Fight_ID
            FROM FightLog
            GROUP BY Fight_ID
            HAVING COUNT(*) = 2
               AND SUM(CASE WHEN Decision = 'W' THEN 1 ELSE 0 END) = 1
        ) singles ON singles.Fight_ID = fw.Fight_ID
        WHERE fw.Decision = 'W'
          AND {' AND '.join(where)}
        ORDER BY RAND()
        LIMIT 1
    """
    rows = select_view_dicts(sql, params)
    if not rows:
        raise RuntimeError("No matching stock-format singles fight found for the given filters")

    row = rows[0]
    fight_type = row["fight_type"]
    total_stocks = STOCK_FIGHT_TYPES[fight_type]
    winner_match_result = int(row["winner_match_result"] or 0)

    is_sudden_death = winner_match_result == 0
    winner_stocks_remaining = winner_match_result if winner_match_result > 0 else 1

    return {
        "match_id": str(uuid.uuid4())[:8],
        "fight_id": int(row["fight_id"]),
        "season": int(row["season"]) if row["season"] is not None else None,
        "month": int(row["month"]) if row["month"] is not None else None,
        "week": int(row["week"]) if row["week"] is not None else None,
        "ppv": row["ppv"],
        "stage": row["stage"],
        "championship": row["championship"],
        "fight_type": fight_type,
        "fighter_a": row["winner"],
        "fighter_b": row["loser"],
        "winner": row["winner"],
        # Constraint payload — synthesizer pins the simulation to this exact result
        "format": "stock",
        "total_stocks": total_stocks,
        "winner_stocks_remaining": winner_stocks_remaining,
        "is_sudden_death": is_sudden_death,
        "winner_match_result": winner_match_result,
        # ELO snapshot at the moment of this fight — used for baseline win prob.
        # `_a` = fighter_a (the winner), `_b` = fighter_b (the loser)
        "elo": {
            "a_before": float(row["winner_elo_before"]) if row["winner_elo_before"] is not None else None,
            "a_after": float(row["winner_elo_after"]) if row["winner_elo_after"] is not None else None,
            "b_before": float(row["loser_elo_before"]) if row["loser_elo_before"] is not None else None,
            "b_after": float(row["loser_elo_after"]) if row["loser_elo_after"] is not None else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pick a historical stock-format singles match and emit it.")
    parser.add_argument("--season", type=int, default=None, help="Restrict to a season")
    parser.add_argument("--ppv", default=None, help="Restrict to a PPV name")
    parser.add_argument("--sink", choices=["stdout", "kafka"], default="stdout")
    args = parser.parse_args()

    match = pick_match(season=args.season, ppv=args.ppv)

    if args.sink == "stdout":
        print(json.dumps(match))
        return

    producer = make_producer()
    try:
        produce_json(producer, TOPIC_SCHEDULED, key=match["match_id"], value=match)
        producer.flush(5)
        score = (
            "SUDDEN DEATH"
            if match["is_sudden_death"]
            else f"{match['total_stocks']}-{match['total_stocks'] - match['winner_stocks_remaining']}"
        )
        print(
            f"Published match {match['match_id']} to {TOPIC_SCHEDULED}: "
            f"{match['fighter_a']} vs {match['fighter_b']} → {match['winner']} ({score})",
            file=sys.stderr,
        )
    finally:
        producer.flush(5)


if __name__ == "__main__":
    main()

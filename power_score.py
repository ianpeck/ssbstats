#!/usr/bin/env python3
"""Power Score: composite fighter ranking by season.

Metrics & weights:
  35% — Avg Season ELO
  30% — Weighted title months  (major month = 2pts, minor month = 1pt)
  20% — Event wins             (tournament/rumble/series/etc wins that season)
  15% — Win %

Each metric is percentile-ranked among all fighters in that season,
then multiplied by its weight to produce the 0–100 composite score.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pymysql

load_dotenv(dotenv_path=Path('secrets.env'))

EVENT_COLS = [
    'Won_Tournament', 'Won_Royal_Rumble', 'Won_Scramble',
    'Won_Smash_Series', 'Won_Money_In_The_Bank', 'Won_Smash_Bros',
]

# Season: ELO carries historical baggage so win% matters more within a season
SEASON_WEIGHTS = {
    'avg_elo':       0.15,
    'wtitle_months': 0.45,
    'event_wins':    0.10,
    'win_pct':       0.30,
}

# Career: ELO is a reliable long-term skill indicator; win% can be inflated
CAREER_WEIGHTS = {
    'avg_elo':       0.35,
    'wtitle_months': 0.40,
    'event_wins':    0.10,
    'win_pct':       0.15,
}

assert abs(sum(SEASON_WEIGHTS.values()) - 1.0) < 1e-9, f"Season weights must sum to 1.0"
assert abs(sum(CAREER_WEIGHTS.values()) - 1.0) < 1e-9, f"Career weights must sum to 1.0"

# Set which weights to use for this run
WEIGHTS = SEASON_WEIGHTS


def get_connection():
    return pymysql.connect(
        host=os.getenv('awsendpoint'),
        database=os.getenv('awsdb'),
        user=os.getenv('awsuser'),
        password=os.getenv('awspassword'),
        port=3306,
    )


def q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params) if params else cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def percentile_rank(vals, v):
    """0–100 percentile: what fraction of peers does v beat?"""
    n = len(vals)
    if n <= 1:
        return 100.0
    below = sum(1 for x in vals if x < v)
    return (below / (n - 1)) * 100.0


def main():
    conn = get_connection()

    seasons = [r['Season'] for r in q(conn,
        "SELECT DISTINCT Season FROM CareerStatsBySeason ORDER BY Season")]

    for season in seasons:
        # --- raw data pulls ---
        season_rows = q(conn,
            "SELECT * FROM CareerStatsBySeason WHERE Season = %s", (season,))

        hol_rows = q(conn,
            "SELECT Fighter_Name, Months_With_Title, Months_With_Major, " +
            ", ".join(EVENT_COLS) +
            " FROM holistic_view WHERE Season = %s", (season,))
        hol = {r['Fighter_Name']: r for r in hol_rows}

        elo_rows = q(conn, """
            SELECT e.fighter_name, ROUND(AVG(e.elo_after), 1) AS avg_elo
            FROM Elo e
            JOIN Fight f ON e.fight_id = f.Fight_ID
            WHERE f.Season_ID = %s
            GROUP BY e.fighter_name
        """, (season,))
        elo = {r['fighter_name']: float(r['avg_elo']) for r in elo_rows}

        # --- build fighter records ---
        fighters = []
        for row in season_rows:
            name = row.get('Fighter_Name') or row.get('fighter_name') or ''
            if not name:
                continue

            try:
                win_pct = float(str(row.get('Win Percentage') or '0').replace('%', ''))
            except (ValueError, TypeError):
                win_pct = 0.0

            h = hol.get(name, {})
            major_m = int(h.get('Months_With_Major') or 0)
            total_m = int(h.get('Months_With_Title') or 0)
            minor_m = total_m - major_m
            # major=2pts, minor=1pt  →  2*major + 1*minor = major + total
            wtitle  = (major_m * 2) + minor_m

            ev_wins = sum(
                1 for col in EVENT_COLS
                if h.get(col) not in (None, '', 'None')
            )

            fighters.append({
                'name':          name,
                'avg_elo':       elo.get(name, 1500.0),
                'wtitle_months': wtitle,
                'event_wins':    ev_wins,
                'win_pct':       win_pct,
                # keep raw for display
                '_major_m':      major_m,
                '_total_m':      total_m,
            })

        if not fighters:
            continue

        # --- percentile rank each metric ---
        for metric in WEIGHTS:
            vals = [f[metric] for f in fighters]
            for f in fighters:
                f[f'{metric}_pct'] = percentile_rank(vals, f[metric])

        # --- composite power score ---
        for f in fighters:
            f['power_score'] = sum(
                WEIGHTS[m] * f[f'{m}_pct'] for m in WEIGHTS
            )

        top5 = sorted(fighters, key=lambda x: x['power_score'], reverse=True)[:5]

        print(f"\n{'='*72}")
        print(f"  SEASON {season}  —  TOP 5 POWER SCORE")
        print(f"{'='*72}")
        print(f"  {'#':<3} {'Fighter':<22} {'Score':>6}  {'Avg ELO':>7}  "
              f"{'WTitle':>6}  {'EvW':>3}  {'Win%':>6}")
        print(f"  {'-'*66}")
        for i, f in enumerate(top5, 1):
            print(
                f"  {i:<3} {f['name']:<22} {f['power_score']:>5.1f}   "
                f"{f['avg_elo']:>7.1f}  "
                f"{f['wtitle_months']:>6}  "
                f"{f['event_wins']:>3}  "
                f"{f['win_pct']:>5.1f}%"
            )

    # --- career aggregate ---
    career_rows = q(conn, "SELECT Fighter_Name, `Win Percentage` AS win_pct FROM careerstats")

    ev_expr = ' + '.join(
        f"SUM(CASE WHEN `{c}` IS NOT NULL AND `{c}` != '' THEN 1 ELSE 0 END)"
        for c in EVENT_COLS
    )
    hol_career = q(conn,
        "SELECT Fighter_Name, "
        "SUM(COALESCE(Months_With_Major, 0)) AS major_months, "
        "SUM(COALESCE(Months_With_Title, 0)) AS champ_months, "
        f"({ev_expr}) AS event_wins "
        "FROM holistic_view GROUP BY Fighter_Name")
    hol_c = {r['Fighter_Name'].lower().strip(): r for r in hol_career}

    elo_career = q(conn,
        "SELECT fighter_name, ROUND(AVG(elo_after), 1) AS avg_elo FROM Elo GROUP BY fighter_name")
    elo_c = {r['fighter_name'].lower().strip(): float(r['avg_elo']) for r in elo_career}

    career_fighters = []
    for row in career_rows:
        name = row.get('Fighter_Name', '')
        if not name:
            continue
        nk = name.lower().strip()
        h = hol_c.get(nk, {})
        major_m = int(h.get('major_months') or 0)
        total_m = int(h.get('champ_months') or 0)
        minor_m = total_m - major_m
        wtitle  = (major_m * 2) + minor_m
        ev_wins = int(h.get('event_wins') or 0)
        try:
            win_pct = float(str(row.get('win_pct') or '0').replace('%', ''))
        except (ValueError, TypeError):
            win_pct = 0.0
        career_fighters.append({
            'name':          name,
            'avg_elo':       elo_c.get(nk, 1500.0),
            'wtitle_months': wtitle,
            'event_wins':    ev_wins,
            'win_pct':       win_pct,
            '_major_m':      major_m,
            '_total_m':      total_m,
        })

    if career_fighters:
        for metric in CAREER_WEIGHTS:
            vals = [f[metric] for f in career_fighters]
            for f in career_fighters:
                f[f'{metric}_pct'] = percentile_rank(vals, f[metric])
        for f in career_fighters:
            f['power_score'] = sum(
                CAREER_WEIGHTS[m] * f[f'{m}_pct'] for m in CAREER_WEIGHTS
            )
        career_fighters.sort(key=lambda x: x['power_score'], reverse=True)

        print(f"\n{'='*72}")
        print(f"  CAREER POWER SCORE  —  ALL TIME")
        print(f"{'='*72}")
        print(f"  {'#':<3} {'Fighter':<22} {'Score':>6}  {'Avg ELO':>7}  "
              f"{'WTitle':>6}  {'EvW':>3}  {'Win%':>6}")
        print(f"  {'-'*66}")
        for i, f in enumerate(career_fighters, 1):
            print(
                f"  {i:<3} {f['name']:<22} {f['power_score']:>5.1f}   "
                f"{f['avg_elo']:>7.1f}  "
                f"{f['wtitle_months']:>6}  "
                f"{f['event_wins']:>3}  "
                f"{f['win_pct']:>5.1f}%"
            )

    conn.close()
    print()


if __name__ == '__main__':
    main()

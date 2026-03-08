#!/usr/bin/env python3
"""Power Score: composite fighter ranking by season.

Metrics & weights:
  Titles  — Weighted title months  (major month = 2pts, minor month = 1pt)
  Win%    — Season/career win percentage
  ELO     — Avg ELO (season avg or career avg)
  Events  — Tournament/rumble/series/etc wins
  SOS     — Avg ELO of opponents beaten (strength of schedule)

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

# Season: ELO carries historical baggage — win%, titles, and SOS cover in-season performance better
SEASON_WEIGHTS = {
    'avg_elo':       0.00,
    'wtitle_months': 0.45,
    'event_wins':    0.10,
    'win_pct':       0.30,
    'sos':           0.15,
}

# Career: ELO + SOS cover quality/skill; win% is redundant with ELO over large samples
CAREER_WEIGHTS = {
    'avg_elo':       0.40,
    'wtitle_months': 0.40,
    'event_wins':    0.10,
    'win_pct':       0.00,
    'sos':           0.10,
}

assert abs(sum(v for v in SEASON_WEIGHTS.values()) - 1.0) < 1e-9, "Season weights must sum to 1.0"
assert abs(sum(CAREER_WEIGHTS.values()) - 1.0) < 1e-9, "Career weights must sum to 1.0"


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


def apply_power_scores(fighters, weights):
    for metric in weights:
        vals = [f[metric] for f in fighters]
        for f in fighters:
            f[f'{metric}_pct'] = percentile_rank(vals, f[metric])
    for f in fighters:
        f['power_score'] = sum(weights[m] * f[f'{m}_pct'] for m in weights)


def print_ranking(fighters, title, weights, top_n=None):
    ranked = sorted(fighters, key=lambda x: x['power_score'], reverse=True)
    if top_n:
        ranked = ranked[:top_n]
    w = weights
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"  weights — ELO:{w['avg_elo']:.0%}  Titles:{w['wtitle_months']:.0%}  "
          f"EvW:{w['event_wins']:.0%}  Win%:{w['win_pct']:.0%}  SOS:{w['sos']:.0%}")
    print(f"{'='*80}")
    print(f"  {'#':<3} {'Fighter':<22} {'Score':>6}  {'Avg ELO':>7}  "
          f"{'WTitle':>6}  {'EvW':>3}  {'Win%':>6}  {'SOS':>7}")
    print(f"  {'-'*74}")
    for i, f in enumerate(ranked, 1):
        print(
            f"  {i:<3} {f['name']:<22} {f['power_score']:>5.1f}   "
            f"{f['avg_elo']:>7.1f}  "
            f"{f['wtitle_months']:>6}  "
            f"{f['event_wins']:>3}  "
            f"{f['win_pct']:>5.1f}%  "
            f"{f['sos']:>7.1f}"
        )


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

        # SOS: avg ELO of opponents beaten this season
        sos_rows = q(conn, """
            SELECT r_win.Fighter_Name, AVG(e_loss.elo_before) AS avg_beaten_elo
            FROM Results r_win
            JOIN Results r_loss ON r_win.Fight_ID = r_loss.Fight_ID
                                AND r_loss.Decision = 'l'
            JOIN Elo e_loss ON r_loss.Fight_ID = e_loss.fight_id
                           AND r_loss.Fighter_Name = e_loss.fighter_name
            JOIN Fight f ON r_win.Fight_ID = f.Fight_ID
            WHERE r_win.Decision = 'w'
              AND f.Season_ID = %s
            GROUP BY r_win.Fighter_Name
        """, (season,))
        sos = {r['Fighter_Name']: float(r['avg_beaten_elo']) for r in sos_rows}

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
                'sos':           sos.get(name, 1500.0),
            })

        if not fighters:
            continue

        apply_power_scores(fighters, SEASON_WEIGHTS)
        print_ranking(fighters, f"SEASON {season}  —  TOP 5", SEASON_WEIGHTS, top_n=5)

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

    # Career SOS: avg ELO of all opponents ever beaten
    sos_career_rows = q(conn, """
        SELECT r_win.Fighter_Name, AVG(e_loss.elo_before) AS avg_beaten_elo
        FROM Results r_win
        JOIN Results r_loss ON r_win.Fight_ID = r_loss.Fight_ID
                            AND r_loss.Decision = 'l'
        JOIN Elo e_loss ON r_loss.Fight_ID = e_loss.fight_id
                       AND r_loss.Fighter_Name = e_loss.fighter_name
        WHERE r_win.Decision = 'w'
        GROUP BY r_win.Fighter_Name
    """)
    sos_c = {r['Fighter_Name'].lower().strip(): float(r['avg_beaten_elo']) for r in sos_career_rows}

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
            'sos':           sos_c.get(nk, 1500.0),
        })

    if career_fighters:
        apply_power_scores(career_fighters, CAREER_WEIGHTS)
        print_ranking(career_fighters, "CAREER POWER SCORE  —  ALL TIME", CAREER_WEIGHTS)

    conn.close()
    print()


if __name__ == '__main__':
    main()

"""
elo.py — Compute ELO ratings for all SmashBros fighters.

Reads from the SmashBros DB, writes results to the Elo table, and outputs a CSV.

TABLE DDL (run once before first use, or pass --create-table):

    CREATE TABLE IF NOT EXISTS Elo (
        elo_id       INT AUTO_INCREMENT PRIMARY KEY,
        result_id    INT           NOT NULL,
        fighter_name VARCHAR(100)  NOT NULL,
        fight_id     INT           NOT NULL,
        elo_before   DECIMAL(10,2) NOT NULL,
        elo_after    DECIMAL(10,2) NOT NULL,
        INDEX idx_result  (result_id),
        INDEX idx_fighter (fighter_name),
        INDEX idx_fight   (fight_id)
    );

Usage:
    python elo.py                # compute, write to DB, write CSV
    python elo.py --csv-only     # skip DB write (dry run)
    python elo.py --create-table # also run the CREATE TABLE DDL before inserting

ELO settings:
    Starting ELO : 1500
    K-factor     : 24
    Scale (S)    : 300

Match type handling:
    1v1      — standard ELO
    FFA      — winner vs each loser as pairwise matchups, each scaled by 1/(n_losers)
               losers don't fight each other (no outcome data between them)
    Tag Team — team rating = avg(member ELOs); one team matchup; ELO change
               split evenly among team members; half the swing of a solo match
    nc       — skipped entirely
"""

import csv
import os
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path('secrets.env'))

# ── ELO constants ─────────────────────────────────────────────────────────────
STARTING_ELO = 1500.0
K            = 24.0
S            = 300.0

_DDL = """
CREATE TABLE IF NOT EXISTS Elo (
    elo_id       INT AUTO_INCREMENT PRIMARY KEY,
    result_id    INT           NOT NULL,
    fighter_name VARCHAR(100)  NOT NULL,
    fight_id     INT           NOT NULL,
    elo_before   DECIMAL(10,2) NOT NULL,
    elo_after    DECIMAL(10,2) NOT NULL,
    INDEX idx_result  (result_id),
    INDEX idx_fighter (fighter_name),
    INDEX idx_fight   (fight_id)
);
""".strip()

CSV_PATH = 'elo_output.csv'


# ── DB connection ──────────────────────────────────────────────────────────────
def get_connection():
    return pymysql.connect(
        host=os.getenv('awsendpoint'),
        database=os.getenv('awsdb'),
        user=os.getenv('awsuser'),
        password=os.getenv('awspassword'),
        port=3306,
    )


# ── Data fetching ──────────────────────────────────────────────────────────────
def fetch_fights(conn):
    """
    Return every decisioned result row in strict chronological order.
    Excludes nc (no contest) decisions.
    """
    sql = """
        SELECT
            r.Result_ID,
            r.Fighter_Name,
            r.Fight_ID,
            LOWER(r.Decision)  AS decision,
            f.Season_ID,
            f.Month,
            f.Week,
            ft.Description     AS fight_type
        FROM Results r
        JOIN Fight    f  ON r.Fight_ID    = f.Fight_ID
        JOIN FightType ft ON f.FightType_ID = ft.FightType_ID
        WHERE LOWER(r.Decision) IN ('w', 'l')
        ORDER BY f.Season_ID, f.Month, f.Week, f.Fight_ID
    """
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


# ── ELO math ───────────────────────────────────────────────────────────────────
def _expected(r_a, r_b):
    """E_A = 1 / (1 + 10^((R_B - R_A) / S))"""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / S))


# ── Core ELO processor ─────────────────────────────────────────────────────────
def compute_elo(rows):
    """
    Process all fights in order and return ELO rows for the Elo table.

    Returns list of tuples: (result_id, fighter_name, fight_id, elo_before, elo_after)

    Match type logic
    ----------------
    1v1  (n=2, any type except Tag Team):
        Standard pairwise. Weight = 1.0.

    FFA  (n≥3, fight_type != 'Tag Team'):
        Winner faces each loser as a separate pairwise matchup.
        Each matchup is scaled by weight = 1/n_losers so the winner's
        total ELO gain ≈ one normal win regardless of match size.
        Losers don't face each other (no outcome data to rank them).

    Tag Team  (fight_type == 'Tag Team'):
        Team A = all winners, Team B = all losers.
        Team rating = avg ELO of members.
        One team-vs-team matchup with full K.
        ELO change is split equally among team members.
        This gives each player ~half the swing of a 1v1, reflecting shared credit.
    """
    # Group rows by fight_id, preserving insertion (chronological) order
    fights = OrderedDict()
    for result_id, fighter_name, fight_id, decision, season, month, week, fight_type in rows:
        if fight_id not in fights:
            fights[fight_id] = {'fight_type': fight_type, 'participants': []}
        fights[fight_id]['participants'].append({
            'result_id':   result_id,
            'fighter_name': fighter_name,
            'decision':    decision,
        })

    ratings = defaultdict(lambda: STARTING_ELO)  # live ELO state for every fighter
    output  = []

    for fight_id, fight in fights.items():
        participants = fight['participants']
        fight_type   = fight['fight_type']

        winners = [p for p in participants if p['decision'] == 'w']
        losers  = [p for p in participants if p['decision'] == 'l']

        if not winners or not losers:
            continue  # skip fights with no clear winner/loser

        # Snapshot ELO before this fight for all participants
        before = {p['fighter_name']: ratings[p['fighter_name']] for p in participants}
        delta  = {p['fighter_name']: 0.0 for p in participants}

        if fight_type == 'Tag Team' and winners and losers:
            # ── Tag Team: one team matchup, split among members ──────────────
            n_w = len(winners)
            n_l = len(losers)

            team_a_rating = sum(before[p['fighter_name']] for p in winners) / n_w
            team_b_rating = sum(before[p['fighter_name']] for p in losers)  / n_l

            e_a          = _expected(team_a_rating, team_b_rating)
            team_a_gain  = K * (1.0 - e_a)          # positive
            team_b_gain  = K * (0.0 - (1.0 - e_a))  # negative (mirror, zero-sum)

            for p in winners:
                delta[p['fighter_name']] += team_a_gain / n_w
            for p in losers:
                delta[p['fighter_name']] += team_b_gain / n_l

        else:
            # ── 1v1 or FFA: winner vs each loser, scaled pairwise ────────────
            # weight = 1/n_losers so winner's total gain ≈ one normal win
            n_l    = len(losers)
            weight = 1.0 / n_l

            for winner in winners:
                w_name = winner['fighter_name']
                for loser in losers:
                    l_name = loser['fighter_name']
                    e_w    = _expected(before[w_name], before[l_name])
                    e_l    = 1.0 - e_w  # exact complement, keeps zero-sum per pair

                    delta[w_name] += K * weight * (1.0 - e_w)
                    delta[l_name] += K * weight * (0.0 - e_l)

        # Apply deltas, record before/after for each result_id
        for p in participants:
            name       = p['fighter_name']
            elo_before = before[name]
            elo_after  = round(elo_before + delta[name], 2)
            ratings[name] = elo_after
            output.append((p['result_id'], name, fight_id, elo_before, elo_after))

    return output


# ── Output ─────────────────────────────────────────────────────────────────────
def write_to_db(conn, records, create_table=False):
    cur = conn.cursor()

    if create_table:
        print('Running CREATE TABLE IF NOT EXISTS Elo ...')
        cur.execute(_DDL)

    cur.execute('DELETE FROM Elo')
    cur.executemany(
        'INSERT INTO Elo (result_id, fighter_name, fight_id, elo_before, elo_after) '
        'VALUES (%s, %s, %s, %s, %s)',
        records,
    )
    conn.commit()
    print(f'Wrote {len(records)} rows to Elo table.')


def write_to_csv(records, path=CSV_PATH):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['result_id', 'fighter_name', 'fight_id', 'elo_before', 'elo_after'])
        writer.writerows(records)
    print(f'CSV written to {path}')


def print_summary(records):
    """Print top 10 and bottom 5 fighters by final ELO."""
    final = {}
    for _, name, _, _, elo_after in records:
        final[name] = elo_after  # last write wins (chronological order)

    ranked = sorted(final.items(), key=lambda x: x[1], reverse=True)
    print(f'\n{"─"*35}')
    print(f'{"Rank":<5} {"Fighter":<22} {"ELO":>6}')
    print(f'{"─"*35}')
    for i, (name, elo) in enumerate(ranked[:10], 1):
        print(f'{i:<5} {name:<22} {elo:>6.1f}')
    print('  ...')
    for i, (name, elo) in enumerate(ranked[-5:], len(ranked) - 4):
        print(f'{i:<5} {name:<22} {elo:>6.1f}')
    print(f'{"─"*35}')
    print(f'Total fighters rated: {len(ranked)}')
    print(f'Total ELO rows: {len(records)}\n')


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    csv_only     = '--csv-only'     in sys.argv
    create_table = '--create-table' in sys.argv

    print('Connecting to SmashBros DB...')
    conn = get_connection()
    try:
        print('Fetching fights...')
        rows    = fetch_fights(conn)
        print(f'Processing {len(rows)} result rows...')
        records = compute_elo(rows)

        print_summary(records)
        write_to_csv(records)

        if not csv_only:
            write_to_db(conn, records, create_table=create_table)
        else:
            print('(--csv-only: skipped DB write)')
    finally:
        conn.close()

import pymysql
import os
from dotenv import load_dotenv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

load_dotenv(dotenv_path=Path('secrets.env'))


def get_connection():
    return pymysql.connect(
        host=os.getenv('awsendpoint'),
        database=os.getenv('awsdb'),
        user=os.getenv('awsuser'),
        password=os.getenv('awspassword'),
        port=3306,
    )


# ---------- Core query helpers (from smashbrosgui/sql.py) ----------

def h2h_query_sql(query, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        fighter_data = cur.fetchone()
        if not fighter_data:
            return [
                {'Fighter': '', 'Wins': '0', 'Losses': '0', 'W/L %': '0.00%'},
                {'Fighter': '', 'Wins': '0', 'Losses': '0', 'W/L %': '0.00%'}
            ]
        f1, f2 = {}, {}
        for i, data in enumerate(fighter_data):
            if i == 0:
                f1['Fighter'] = data
            elif i == 1:
                f1['Wins'] = str(data)
                f2['Losses'] = str(data)
            elif i == 2:
                f1['W/L %'] = data
            elif i == 3:
                f2['Fighter'] = data
            elif i == 4:
                f2['Wins'] = str(data)
                f1['Losses'] = str(data)
            elif i == 5:
                f2['W/L %'] = data
        return [f1, f2]
    finally:
        conn.close()


def select_list(query, columnnumber, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return [row[columnnumber] for row in cur.fetchall()]
    finally:
        conn.close()


def select_view_row(query, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return list(cur.fetchall())
    finally:
        conn.close()


def select_view_dicts(query, params=None):
    """Like select_view_row but returns list of dicts with column names."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------- Autocomplete data ----------

def get_all_fighters():
    return select_list("SELECT * FROM Fighter", 0)


def get_all_locations():
    return select_list("SELECT * FROM Location", 1)


def get_all_fight_types():
    return select_list("SELECT * FROM FightType", 1)


def get_all_ppvs():
    return select_list("SELECT * FROM PPV", 1)


def get_all_championships():
    return select_list("SELECT * FROM Championship", 1)


def get_all_brands():
    return select_list("SELECT * FROM Brand", 1)


# ---------- Fighter profile data ----------

def get_fighter_career_stats(name):
    """Get all career stats for a single fighter."""
    stats = {}

    queries = {
        'career': ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (name,)),
        'by_location': ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s", (name,)),
        'by_fight_type': ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s", (name,)),
        'by_season': ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s", (name,)),
        'by_brand': ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s", (name,)),
        'by_ppv': ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s", (name,)),
        'championship': ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (name,)),
        'defending_title': ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (name,)),
    }

    def run_query(key_query):
        key, (query, params) = key_query
        try:
            return key, select_view_row(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run_query, queries.items()))

    for key, data in results:
        stats[key] = data

    return stats


# ---------- Fighter accolades (new views) ----------

def get_fighter_accolades(name):
    """Run all accolade-related queries in parallel."""
    queries = {
        'champ_reigns':   ("SELECT Championship_Name, COUNT(*) as reign_count, SUM(months_held) as total_months FROM ChampionshipHistory WHERE Fighter_Name = %s GROUP BY Championship_Name ORDER BY Championship_Name", (name,)),
        'awards':         ("SELECT ah.Season_ID, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Fighter_Name = %s ORDER BY ah.Season_ID DESC", (name,)),
        'win_streaks':    ("SELECT * FROM longestwinstreaks WHERE Fighter_Name = %s", (name,)),
        'loss_streaks':   ("SELECT * FROM longestlosingstreaks WHERE Fighter_Name = %s", (name,)),
        'active_win':     ("SELECT Win_Streak FROM allwinstreaks WHERE Fighter_Name = %s AND Active_Win_Streak = 'Active'", (name,)),
        'active_loss':    ("SELECT Losing_Streak FROM alllosingsteaks WHERE Fighter_Name = %s AND Active_Losing_Streak = 'Active'", (name,)),
        'current_titles': ("SELECT Championship_Name FROM CurrentChampions WHERE Fighter_Name = %s", (name,)),
        'champ_by_champ': ("SELECT * FROM champfightstatsbychampionship WHERE Fighter_Name = %s", (name,)),
        'holistic':       ("SELECT * FROM holistic_view WHERE Fighter_Name = %s ORDER BY Season", (name,)),
    }

    def run_query(key_query):
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=9) as pool:
        results = list(pool.map(run_query, queries.items()))

    return {key: data for key, data in results}


def get_current_champions():
    """Return {Fighter_Name: [Championship_Name, ...]} for all current champions."""
    rows = select_view_dicts("SELECT * FROM CurrentChampions")
    result = {}
    for row in rows:
        result.setdefault(row['Fighter_Name'], []).append(row['Championship_Name'])
    return result


# ---------- Leaderboard ----------

def get_leaderboard():
    """Get all fighters with career stats, sorted by win rate."""
    rows = select_view_row("SELECT * FROM careerstats ORDER BY Fighter_Name")
    fighters = []
    for row in rows:
        fighters.append({
            'name': row[0],
            'wins': row[1] if len(row) > 1 else 0,
            'losses': row[2] if len(row) > 2 else 0,
            'win_pct': row[3] if len(row) > 3 else '0.00%',
        })
    # Sort by win percentage descending
    def parse_pct(pct):
        try:
            if isinstance(pct, str):
                return float(pct.replace('%', ''))
            return float(pct)
        except (ValueError, TypeError):
            return 0.0
    fighters.sort(key=lambda f: parse_pct(f['win_pct']), reverse=True)
    return fighters


# ---------- Seasons ----------

def get_all_seasons():
    """Get all distinct seasons in ascending order."""
    return select_list("SELECT DISTINCT Season FROM CareerStatsBySeason ORDER BY Season", 0)


def get_leaderboard_by_season(season):
    """Get all fighters with stats for a specific season, sorted by win rate."""
    rows = select_view_row(
        "SELECT * FROM CareerStatsBySeason WHERE Season = %s ORDER BY Fighter_Name",
        (season,)
    )
    fighters = []
    for row in rows:
        fighters.append({
            'name': row[0],
            'wins': row[2] if len(row) > 2 else 0,
            'losses': row[3] if len(row) > 3 else 0,
            'win_pct': row[4] if len(row) > 4 else '0.00%',
        })
    def parse_pct(pct):
        try:
            return float(str(pct).replace('%', ''))
        except (ValueError, TypeError):
            return 0.0
    fighters.sort(key=lambda f: parse_pct(f['win_pct']), reverse=True)
    return fighters


def get_season_summary(season):
    """Get full season summary: rankings, awards, holistic accolades."""
    queries = {
        'rankings':     ("SELECT * FROM CareerStatsBySeason WHERE Season = %s", (season,)),
        'awards':       ("SELECT ah.Fighter_Name, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Season_ID = %s ORDER BY a.Award_Name", (season,)),
        'holistic':     ("SELECT * FROM holistic_view WHERE Season = %s", (season,)),
        'champ_history':("SELECT * FROM ChampionshipHistory WHERE Season_Won <= %s AND (Season_Lost IS NULL OR Season_Lost >= %s) ORDER BY Championship_Name, Season_Won, Month_Won", (season, season)),
    }

    def run_query(key_query):
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run_query, queries.items()))

    return {key: data for key, data in results}


def get_fight_log(filters, page=1, per_page=50):
    """Return paginated fight log rows grouped by Fight_ID.

    filters dict keys (all optional, pass empty string to skip):
        season, month, fight_type, location, ppv, championship, fighter, brand
    Column names assumed in FightLog view:
        Fight_ID, Fighter_Name, Season, Month, Week, PPV, Location_Name,
        FightType, Championship_Name, Brand, Win, Stocks_Remaining, Stocks_Taken
    """
    conditions = []
    params = []

    mapping = [
        ('season',       'Season'),
        ('month',        'Month'),
        ('fight_type',   'FightType'),
        ('location',     'Location_Name'),
        ('ppv',          'PPV'),
        ('championship', 'Championship_Name'),
        ('fighter',      'Fighter_Name'),
        ('brand',        'Brand'),
    ]

    for key, col in mapping:
        val = filters.get(key, '')
        if val:
            conditions.append(f"{col} = %s")
            params.append(val)

    where  = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page

    # Paginate by distinct Fight_ID, then fetch all rows for those fights
    sql = f"""
        SELECT fl.*
        FROM FightLog fl
        INNER JOIN (
            SELECT DISTINCT Fight_ID
            FROM FightLog {where}
            ORDER BY Season DESC, Month DESC, Week DESC, Fight_ID DESC
            LIMIT %s OFFSET %s
        ) ids ON fl.Fight_ID = ids.Fight_ID
        ORDER BY fl.Season DESC, fl.Month DESC, fl.Week DESC, fl.Fight_ID DESC,
                 fl.Win DESC, fl.Fighter_Name
    """
    rows = select_view_dicts(sql, params + [per_page, offset])

    # Group by Fight_ID preserving order
    fights = {}
    fight_order = []
    for row in rows:
        fid = row.get('Fight_ID')
        if fid not in fights:
            fights[fid] = {
                'fight_id':    fid,
                'season':      row.get('Season'),
                'month':       row.get('Month'),
                'week':        row.get('Week'),
                'ppv':         row.get('PPV'),
                'location':    row.get('Location_Name') or row.get('Location'),
                'fight_type':  row.get('FightType')     or row.get('Fight_Type'),
                'championship':row.get('Championship_Name') or row.get('Championship'),
                'brand':       row.get('Brand'),
                'fighters':    [],
            }
            fight_order.append(fid)
        fights[fid]['fighters'].append({
            'name':             row.get('Fighter_Name') or row.get('Fighter'),
            'win':              row.get('Win'),
            'stocks_remaining': row.get('Stocks_Remaining'),
            'stocks_taken':     row.get('Stocks_Taken'),
        })

    return [fights[fid] for fid in fight_order]


def get_championship_history_alltime():
    """Full championship history across all seasons, ordered chronologically."""
    return select_view_dicts(
        "SELECT * FROM ChampionshipHistory ORDER BY Championship_Name, Season_Won, Month_Won"
    )


def get_championship_history_by_season_alltime():
    """Championship history split by season for proportional timeline rendering."""
    return select_view_dicts(
        "SELECT * FROM ChampionshipHistoryBySeason ORDER BY Championship_Name, Season, Month_Won, Fighter_Name"
    )


# ---------- Head-to-Head (parallel, same as DatabaseWorker) ----------

def get_h2h_data(fighter1, fighter2, filters):
    """Run all 23 queries in parallel and return structured results."""
    map_name = filters.get('map', '')
    match_type = filters.get('matchType', '')
    season = filters.get('season', '')
    month = filters.get('month', '')
    ppv = filters.get('ppv', '')
    brand = filters.get('brand', '')

    individual_queries = [
        ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s AND Location_Name = %s", (fighter1, map_name)),
        ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s AND Location_Name = %s", (fighter2, map_name)),
        ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s AND FightType = %s", (fighter1, match_type)),
        ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s AND FightType = %s", (fighter2, match_type)),
        ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s AND PPV = %s", (fighter1, ppv)),
        ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s AND PPV = %s", (fighter2, ppv)),
        ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s AND Season = %s", (fighter1, season)),
        ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s AND Season = %s", (fighter2, season)),
        ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s AND Brand = %s", (fighter1, brand)),
        ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s AND Brand = %s", (fighter2, brand)),
    ]

    stored_procedures = [
        ("call SmashBros.headtohead(%s, %s)", (fighter1, fighter2)),
        ("call SmashBros.headtoheadLocation(%s, %s, %s)", (fighter1, fighter2, map_name)),
        ("call SmashBros.headtoheadFightType(%s, %s, %s)", (fighter1, fighter2, match_type)),
        ("call SmashBros.headtoheadSeason(%s, %s, %s)", (fighter1, fighter2, season)),
        ("call SmashBros.headtoheadMonth(%s, %s, %s)", (fighter1, fighter2, month)),
        ("call SmashBros.headtoheadChamp(%s, %s)", (fighter1, fighter2)),
        ("call SmashBros.headtoheadPPV(%s, %s, %s)", (fighter1, fighter2, ppv)),
    ]

    def run_individual(qp):
        try:
            return select_view_row(qp[0], qp[1])
        except Exception:
            return None

    def run_h2h(qp):
        try:
            return h2h_query_sql(qp[0], qp[1])
        except Exception:
            return [
                {'Fighter': '', 'Wins': '0', 'Losses': '0', 'W/L %': '0.00%'},
                {'Fighter': '', 'Wins': '0', 'Losses': '0', 'W/L %': '0.00%'}
            ]

    with ThreadPoolExecutor(max_workers=23) as pool:
        individual_results = list(pool.map(run_individual, individual_queries))
        h2h_results = list(pool.map(run_h2h, stored_procedures))

    # Format individual stats into rows 7-14 for each fighter
    row_labels = [
        'at Location', 'for Match Type', 'in Championship matches',
        'at PPV', 'when Defending a Title', 'Total Record',
        'Season Record', 'On Brand'
    ]
    f1_individual = []
    f2_individual = []
    for i, data in enumerate(individual_results):
        entry = {'wins': '0', 'losses': '0', 'wl_pct': '0.00%'}
        if data and len(data) > 0:
            row = data[0]
            entry = {'wins': str(row[-3]), 'losses': str(row[-2]), 'wl_pct': str(row[-1])}
        if i % 2 == 0:
            f1_individual.append(entry)
        else:
            f2_individual.append(entry)

    # Format H2H stats into rows 0-6
    h2h_labels = [
        'Vs. Other Fighter (Total)', 'Vs. Other Fighter (At Location)',
        'Vs. Other Fighter (Match Type)', 'Vs. Other Fighter (in Season)',
        'Vs. Other Fighter (in Month)', 'Vs. Other Fighter (for Championship)',
        'Vs. Other Fighter (at PPV)'
    ]
    f1_h2h = []
    f2_h2h = []
    for pair in h2h_results:
        f1_h2h.append({'wins': pair[0].get('Wins', '0'), 'losses': pair[0].get('Losses', '0'), 'wl_pct': pair[0].get('W/L %', '0.00%')})
        f2_h2h.append({'wins': pair[1].get('Wins', '0'), 'losses': pair[1].get('Losses', '0'), 'wl_pct': pair[1].get('W/L %', '0.00%')})

    return {
        'fighter1': {
            'name': fighter1,
            'h2h': [{'label': h2h_labels[i], **f1_h2h[i]} for i in range(len(f1_h2h))],
            'individual': [{'label': row_labels[i], **f1_individual[i]} for i in range(len(f1_individual))],
        },
        'fighter2': {
            'name': fighter2,
            'h2h': [{'label': h2h_labels[i], **f2_h2h[i]} for i in range(len(f2_h2h))],
            'individual': [{'label': row_labels[i], **f2_individual[i]} for i in range(len(f2_individual))],
        }
    }

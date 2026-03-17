import math
from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories.base import nk, select_view_dicts


SOS_CAREER_SQL = """
    SELECT r_win.Fighter_Name, AVG(e_loss.elo_before) AS sos
    FROM Results r_win
    JOIN Results r_loss ON r_win.Fight_ID = r_loss.Fight_ID AND r_loss.Decision = 'l'
    JOIN Elo e_loss ON r_loss.Fight_ID = e_loss.fight_id
                   AND r_loss.Fighter_Name = e_loss.fighter_name
    WHERE r_win.Decision = 'w'
    GROUP BY r_win.Fighter_Name
"""

SOS_SEASON_SQL = """
    SELECT r_win.Fighter_Name, AVG(e_loss.elo_before) AS sos
    FROM Results r_win
    JOIN Results r_loss ON r_win.Fight_ID = r_loss.Fight_ID AND r_loss.Decision = 'l'
    JOIN Elo e_loss ON r_loss.Fight_ID = e_loss.fight_id
                   AND r_loss.Fighter_Name = e_loss.fighter_name
    JOIN Fight f ON r_win.Fight_ID = f.Fight_ID
    WHERE r_win.Decision = 'w' AND f.Season_ID = %s
    GROUP BY r_win.Fighter_Name
"""

SOS_ALL_SEASONS_SQL = """
    SELECT r_win.Fighter_Name, f.Season_ID AS season, AVG(e_loss.elo_before) AS sos
    FROM Results r_win
    JOIN Results r_loss ON r_win.Fight_ID = r_loss.Fight_ID AND r_loss.Decision = 'l'
    JOIN Elo e_loss ON r_loss.Fight_ID = e_loss.fight_id
                   AND r_loss.Fighter_Name = e_loss.fighter_name
    JOIN Fight f ON r_win.Fight_ID = f.Fight_ID
    WHERE r_win.Decision = 'w'
    GROUP BY r_win.Fighter_Name, f.Season_ID
"""

CHAMP_WINS_SEASON_SQL = """
    SELECT fl.Fighter_Name,
           SUM(CASE WHEN ch.Championship_Tier = 'Major' THEN 2.2 ELSE 1 END) AS champ_wins
    FROM FightLog fl
    JOIN (SELECT DISTINCT Championship_Name, Championship_Tier FROM ChampionshipHistory) ch
      ON fl.Championship_Name = ch.Championship_Name
    WHERE fl.Championship_Name IS NOT NULL AND fl.Championship_Name != ''
      AND fl.Decision IN ('w', 'W')
      AND fl.Season = %s
    GROUP BY fl.Fighter_Name
"""

CHAMP_WINS_ALL_SEASONS_SQL = """
    SELECT fl.Fighter_Name, fl.Season AS season,
           SUM(CASE WHEN ch.Championship_Tier = 'Major' THEN 2.2 ELSE 1 END) AS champ_wins
    FROM FightLog fl
    JOIN (SELECT DISTINCT Championship_Name, Championship_Tier FROM ChampionshipHistory) ch
      ON fl.Championship_Name = ch.Championship_Name
    WHERE fl.Championship_Name IS NOT NULL AND fl.Championship_Name != ''
      AND fl.Decision IN ('w', 'W')
    GROUP BY fl.Fighter_Name, fl.Season
"""

CHAMP_WINS_CAREER_SQL = """
    SELECT fl.Fighter_Name,
           SUM(CASE WHEN ch.Championship_Tier = 'Major' THEN 2.2 ELSE 1 END) AS champ_wins
    FROM FightLog fl
    JOIN (SELECT DISTINCT Championship_Name, Championship_Tier FROM ChampionshipHistory) ch
      ON fl.Championship_Name = ch.Championship_Name
    WHERE fl.Championship_Name IS NOT NULL AND fl.Championship_Name != ''
      AND fl.Decision IN ('w', 'W')
    GROUP BY fl.Fighter_Name
"""

SEASON_POWER_WEIGHTS = {
    "avg_elo": 0.00,
    "champ_wins": 0.45,
    "event_wins": 0.05,
    "win_pct": 0.30,
    "sos": 0.20,
}

CAREER_POWER_WEIGHTS = {
    "avg_elo": 0.50,
    "champ_wins": 0.45,
    "event_wins": 0.05,
    "win_pct": 0.00,
    "sos": 0.00,
}

POWER_EVENT_WEIGHTS = {
    "Won_Tournament":        0.40,
    "Won_Royal_Rumble":      0.05,
    "Won_Scramble":          0.10,
    "Won_Smash_Series":      0.05,
    "Won_Money_In_The_Bank": 0.05,
    "Won_Smash_Bros":        0.35,
}
POWER_EVENT_COLS = list(POWER_EVENT_WEIGHTS.keys())


def apply_power_scores(fighters, weights, all_time_maxes):
    """Apply sqrt-normalized metric weights using all-time maxes as the ceiling."""
    if not fighters:
        return

    def to_float(value):
        try:
            return float(str(value).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    for fighter in fighters:
        score = 0.0
        raw_vals = {
            "avg_elo": float(fighter.get("avg_elo") or 1500),
            "champ_wins": float(fighter.get("champ_wins") or 0),
            "event_wins": float(fighter.get("event_wins") or 0),
            "win_pct": to_float(fighter.get("win_pct", "0")),
            "sos": float(fighter.get("sos") or 1500),
        }
        for metric, weight in weights.items():
            if weight == 0:
                continue
            ceiling = all_time_maxes.get(metric, 1)
            if ceiling <= 0:
                ceiling = 1
            normalized = min(math.sqrt(raw_vals[metric] / ceiling) * 100.0, 100.0)
            score += weight * normalized
        fighter["power_score"] = round(score, 1)

    ranked = sorted(fighters, key=lambda item: item["power_score"], reverse=True)
    for i, fighter in enumerate(ranked, 1):
        fighter["power_rank"] = i


def get_all_season_power_scores():
    """Return season power scores keyed by season then lowercase fighter name."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_s = pool.submit(select_view_dicts, "SELECT Fighter_Name, Season, `Win Percentage` AS win_pct FROM CareerStatsBySeason")
        f_h = pool.submit(select_view_dicts, "SELECT Fighter_Name, Season, " + ", ".join(f"`{col}`" for col in POWER_EVENT_COLS) + " FROM holistic_view")
        f_e = pool.submit(select_view_dicts, """
            SELECT e.fighter_name, f.Season_ID AS season, ROUND(AVG(e.elo_after), 1) AS avg_elo
            FROM Elo e JOIN Fight f ON e.fight_id = f.Fight_ID
            GROUP BY e.fighter_name, f.Season_ID
        """)
        f_sos = pool.submit(select_view_dicts, SOS_ALL_SEASONS_SQL)
        f_cw = pool.submit(select_view_dicts, CHAMP_WINS_ALL_SEASONS_SQL)
        season_rows = f_s.result()
        hol_rows = f_h.result()
        elo_rows = f_e.result()
        sos_rows = f_sos.result()
        cw_rows = f_cw.result()

    hol = {}
    for row in hol_rows:
        hol[(int(row.get("Season") or 0), nk(row.get("Fighter_Name", "")))] = row
    elo = {(int(row.get("season") or 0), nk(row.get("fighter_name", ""))): float(row.get("avg_elo") or 1500) for row in elo_rows}
    sos = {(int(row.get("season") or 0), nk(row.get("Fighter_Name", ""))): float(row.get("sos") or 1500) for row in sos_rows}
    champ = {(int(row.get("season") or 0), nk(row.get("Fighter_Name", ""))): float(row.get("champ_wins") or 0) for row in cw_rows}

    by_season = {}
    for row in season_rows:
        by_season.setdefault(int(row.get("Season") or 0), []).append(row)

    # Build all fighter records first to compute all-time maxes
    all_season_fighters = {}
    for season, rows in by_season.items():
        fighters = []
        for row in rows:
            name = row.get("Fighter_Name", "")
            if not name:
                continue
            hol_row = hol.get((season, nk(name)), {})
            ev = sum(POWER_EVENT_WEIGHTS[col] for col in POWER_EVENT_COLS if hol_row.get(col) not in (None, "", "None"))
            fighters.append({
                "name": name,
                "avg_elo": elo.get((season, nk(name)), 1500.0),
                "champ_wins": champ.get((season, nk(name)), 0),
                "event_wins": ev,
                "win_pct": str(row.get("win_pct") or "0"),
                "sos": sos.get((season, nk(name)), 1500.0),
            })
        if fighters:
            all_season_fighters[season] = fighters

    # Compute all-time maxes across every season
    all_time_maxes = {}
    for metric in SEASON_POWER_WEIGHTS:
        def to_float_val(value):
            try:
                return float(str(value).replace("%", ""))
            except (ValueError, TypeError):
                return 0.0
        all_vals = [to_float_val(f[metric]) for fighters in all_season_fighters.values() for f in fighters]
        all_time_maxes[metric] = max(all_vals) if all_vals else 1

    # Score each season using the shared ceiling
    result = {}
    for season in by_season:
        fighters = all_season_fighters.get(season)
        if not fighters:
            continue
        apply_power_scores(fighters, SEASON_POWER_WEIGHTS, all_time_maxes)
        result[season] = {nk(fighter["name"]): {"power_score": fighter["power_score"], "power_rank": fighter["power_rank"]} for fighter in fighters}
    return result


def get_season_power_scores(season):
    """Return power scores for a single season keyed by lowercase fighter name."""
    return get_all_season_power_scores().get(season, {})


def get_career_power_scores():
    """Return career power scores keyed by lowercase fighter name."""
    ev_expr = " + ".join(f"SUM(CASE WHEN `{col}` IS NOT NULL AND `{col}` != '' THEN {POWER_EVENT_WEIGHTS[col]} ELSE 0 END)" for col in POWER_EVENT_COLS)
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_c = pool.submit(select_view_dicts, "SELECT Fighter_Name, `Win Percentage` AS win_pct FROM careerstats")
        f_h = pool.submit(select_view_dicts, "SELECT Fighter_Name, " + f"({ev_expr}) AS event_wins " + "FROM holistic_view GROUP BY Fighter_Name")
        f_e = pool.submit(select_view_dicts, "SELECT fighter_name, ROUND(AVG(elo_after), 1) AS avg_elo FROM Elo GROUP BY fighter_name")
        f_sos = pool.submit(select_view_dicts, SOS_CAREER_SQL)
        f_cw = pool.submit(select_view_dicts, CHAMP_WINS_CAREER_SQL)
        career_rows = f_c.result()
        hol_rows = f_h.result()
        elo_rows = f_e.result()
        sos_rows = f_sos.result()
        cw_rows = f_cw.result()

    hol_lookup = {nk(row["Fighter_Name"]): row for row in hol_rows}
    elo_lookup = {nk(row["fighter_name"]): float(row["avg_elo"]) for row in elo_rows}
    sos_lookup = {nk(row["Fighter_Name"]): float(row["sos"]) for row in sos_rows}
    champ_lookup = {nk(row["Fighter_Name"]): float(row["champ_wins"]) for row in cw_rows}

    fighters = []
    for row in career_rows:
        name = row.get("Fighter_Name", "")
        if not name:
            continue
        hol_row = hol_lookup.get(nk(name), {})
        fighters.append({
            "name": name,
            "avg_elo": elo_lookup.get(nk(name), 1500.0),
            "champ_wins": champ_lookup.get(nk(name), 0),
            "event_wins": float(hol_row.get("event_wins") or 0),
            "win_pct": str(row.get("win_pct") or "0"),
            "sos": sos_lookup.get(nk(name), 1500.0),
        })

    # Career uses its own pool maxes
    def to_float_val(value):
        try:
            return float(str(value).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0
    career_maxes = {}
    for metric in CAREER_POWER_WEIGHTS:
        vals = [to_float_val(f[metric]) for f in fighters]
        career_maxes[metric] = max(vals) if vals else 1

    apply_power_scores(fighters, CAREER_POWER_WEIGHTS, career_maxes)
    total = len(fighters)
    return {
        nk(fighter["name"]): {"power_score": fighter["power_score"], "power_rank": fighter["power_rank"], "total_fighters": total}
        for fighter in fighters
    }

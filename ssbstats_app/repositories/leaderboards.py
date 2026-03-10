from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories.base import nk, select_view_dicts, select_view_row
from ssbstats_app.repositories.elo import get_elo_for_leaderboard, get_elo_for_leaderboard_by_season
from ssbstats_app.repositories.lookups import get_canonical_name_map
from ssbstats_app.repositories.power import CAREER_POWER_WEIGHTS, SEASON_POWER_WEIGHTS, SOS_CAREER_SQL, SOS_SEASON_SQL, apply_power_scores


EVENT_COLS_LB = [
    "Won_Tournament",
    "Won_Royal_Rumble",
    "Won_Scramble",
    "Won_Smash_Series",
    "Won_Money_In_The_Bank",
    "Won_Smash_Bros",
]


def row_name(row):
    """Return the fighter-name field from a dict row regardless of casing."""
    for key in ("Fighter_Name", "fighter_name", "Name", "name"):
        if row.get(key):
            return str(row[key])
    for key, value in row.items():
        if "name" in key.lower() and value:
            return str(value)
    return None


def get_leaderboard():
    """Return the all-time leaderboard enriched with accolade and Elo metrics."""
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_career = pool.submit(select_view_row, "SELECT * FROM careerstats ORDER BY Fighter_Name")
        f_hol = pool.submit(select_view_dicts, "SELECT Fighter_Name, Months_With_Title, Months_With_Major, " + ", ".join(EVENT_COLS_LB) + " FROM holistic_view")
        f_titles = pool.submit(select_view_dicts, "SELECT Fighter_Name, COUNT(DISTINCT Championship_Name) as unique_titles FROM ChampionshipHistory GROUP BY Fighter_Name")
        f_tc = pool.submit(select_view_dicts, "SELECT * FROM triplecrown")
        f_elo = pool.submit(get_elo_for_leaderboard)
        f_sos = pool.submit(select_view_dicts, SOS_CAREER_SQL)
        career_rows = f_career.result()
        try:
            holistic_all = f_hol.result()
        except Exception:
            try:
                holistic_all = select_view_dicts("SELECT Fighter_Name, Months_With_Title, " + ", ".join(EVENT_COLS_LB) + " FROM holistic_view")
            except Exception:
                holistic_all = []
        titles_rows = f_titles.result()
        tc_rows = f_tc.result() if not f_tc.exception() else []
        elo_by_fighter = f_elo.result() if not f_elo.exception() else {}
        sos_rows = f_sos.result() if not f_sos.exception() else []

    sos_by_fighter = {nk(row["Fighter_Name"]): float(row["sos"]) for row in sos_rows}
    hol_by_fighter = {}
    for row in holistic_all:
        hol_by_fighter.setdefault(nk(row["Fighter_Name"]), []).append(row)
    titles_by_fighter = {nk(row["Fighter_Name"]): int(row["unique_titles"] or 0) for row in titles_rows}
    tc_fighters = {nk(row_name(row)) for row in tc_rows if row_name(row)}

    fighters = []
    for row in career_rows:
        name = row[0]
        wins = int(row[1]) if len(row) > 1 else 0
        losses = int(row[2]) if len(row) > 2 else 0
        win_pct = row[3] if len(row) > 3 else "0.00%"
        hol = hol_by_fighter.get(nk(name), [])
        champ_months = sum(int(r.get("Months_With_Title") or 0) for r in hol)
        major_months = sum(int(r.get("Months_With_Major") or 0) for r in hol)
        event_set = set()
        for hol_row in hol:
            for col in EVENT_COLS_LB:
                if hol_row.get(col) not in (None, "", "None"):
                    event_set.add(col)
        elo = elo_by_fighter.get(nk(name), {})
        fighters.append({
            "name": name,
            "wins": wins,
            "losses": losses,
            "win_pct": win_pct,
            "total_fights": wins + losses,
            "champ_months": champ_months,
            "major_months": major_months,
            "event_wins": len(event_set),
            "unique_titles": titles_by_fighter.get(nk(name), 0),
            "triple_crown": 1 if nk(name) in tc_fighters else 0,
            "current_elo": float(elo["current_elo"]) if elo.get("current_elo") is not None else None,
            "avg_elo": float(elo["avg_elo"]) if elo.get("avg_elo") is not None else None,
            "peak_elo": float(elo["peak_elo"]) if elo.get("peak_elo") is not None else None,
            "sos": sos_by_fighter.get(nk(name), 1500.0),
        })

    def parse_pct(pct):
        """Parse a percentage string into a sortable float."""
        try:
            return float(str(pct).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    fighters.sort(key=lambda fighter: parse_pct(fighter["win_pct"]), reverse=True)
    apply_power_scores(fighters, CAREER_POWER_WEIGHTS)
    return fighters


def get_leaderboard_by_season(season):
    """Return leaderboard rows for a single season with season-scoped metrics."""
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_season = pool.submit(select_view_dicts, "SELECT * FROM CareerStatsBySeason WHERE Season = %s ORDER BY Fighter_Name", (season,))
        f_hol = pool.submit(select_view_dicts, "SELECT Fighter_Name, Months_With_Title, Months_With_Major, " + ", ".join(EVENT_COLS_LB) + " FROM holistic_view WHERE Season = %s", (season,))
        f_titles = pool.submit(select_view_dicts, "SELECT Fighter_Name, COUNT(DISTINCT Championship_Name) as unique_titles FROM ChampionshipHistory WHERE Season_Won <= %s AND (Season_Lost IS NULL OR Season_Lost >= %s) GROUP BY Fighter_Name", (season, season))
        f_elo = pool.submit(get_elo_for_leaderboard_by_season, season)
        f_canonical = pool.submit(get_canonical_name_map)
        f_sos = pool.submit(select_view_dicts, SOS_SEASON_SQL, (season,))
        season_rows = f_season.result()
        canonical_map = f_canonical.result()
        try:
            holistic_all = f_hol.result()
        except Exception:
            try:
                holistic_all = select_view_dicts("SELECT Fighter_Name, Months_With_Title, " + ", ".join(EVENT_COLS_LB) + " FROM holistic_view WHERE Season = %s", (season,))
            except Exception:
                holistic_all = []
        titles_rows = f_titles.result()
        elo_by_fighter = f_elo.result() if not f_elo.exception() else {}
        sos_rows = f_sos.result() if not f_sos.exception() else []

    sos_by_fighter = {nk(row["Fighter_Name"]): float(row["sos"]) for row in sos_rows}
    hol_by_fighter = {}
    for row in holistic_all:
        hol_by_fighter.setdefault(nk(row["Fighter_Name"]), []).append(row)
    titles_by_fighter = {nk(row["Fighter_Name"]): int(row["unique_titles"] or 0) for row in titles_rows}

    fighters = []
    for row in season_rows:
        raw_name = row.get("Fighter_Name") or row.get("fighter_name") or ""
        name = canonical_map.get(raw_name.lower(), raw_name)
        wins = int(row.get("Wins") or row.get("wins") or 0)
        losses = int(row.get("Losses") or row.get("losses") or 0)
        win_pct = row.get("Win Percentage") or row.get("win_pct") or "0.00%"
        hol = hol_by_fighter.get(nk(name), [])
        champ_months = sum(int(r.get("Months_With_Title") or 0) for r in hol)
        major_months = sum(int(r.get("Months_With_Major") or 0) for r in hol)
        event_set = set()
        for hol_row in hol:
            for col in EVENT_COLS_LB:
                if hol_row.get(col) not in (None, "", "None"):
                    event_set.add(col)
        elo = elo_by_fighter.get(nk(name), {})
        fighters.append({
            "name": name,
            "wins": wins,
            "losses": losses,
            "win_pct": win_pct,
            "total_fights": wins + losses,
            "champ_months": champ_months,
            "major_months": major_months,
            "event_wins": len(event_set),
            "unique_titles": titles_by_fighter.get(nk(name), 0),
            "triple_crown": 0,
            "peak_season_elo": float(elo["peak_season_elo"]) if elo.get("peak_season_elo") is not None else None,
            "avg_elo": float(elo["avg_elo"]) if elo.get("avg_elo") is not None else None,
            "season_end_elo": float(elo["season_end_elo"]) if elo.get("season_end_elo") is not None else None,
            "sos": sos_by_fighter.get(nk(name), 1500.0),
        })

    def parse_pct(pct):
        """Parse a percentage string into a sortable float."""
        try:
            return float(str(pct).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    fighters.sort(key=lambda fighter: parse_pct(fighter["win_pct"]), reverse=True)
    apply_power_scores(fighters, SEASON_POWER_WEIGHTS)
    return fighters

from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories.base import select_view_dicts, select_view_row


def get_fighter_career_stats(name):
    """Return grouped career-stat datasets for a single fighter."""
    stats = {}
    queries = {
        "career": ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (name,)),
        "by_location": ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s", (name,)),
        "by_fight_type": ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s", (name,)),
        "by_season": ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s", (name,)),
        "by_brand": ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s", (name,)),
        "by_ppv": ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s", (name,)),
        "championship": ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (name,)),
        "defending_title": ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (name,)),
    }

    def run_query(key_query):
        """Execute one fighter-stat query and fall back to an empty list on failure."""
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


def get_fighter_accolades(name):
    """Return accolade, streak, and title datasets for a single fighter."""
    queries = {
        "champ_reigns": ("SELECT Championship_Name, COUNT(*) as reign_count, SUM(months_held) as total_months FROM ChampionshipHistory WHERE Fighter_Name = %s GROUP BY Championship_Name ORDER BY Championship_Name", (name,)),
        "awards": ("SELECT ah.Season_ID, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Fighter_Name = %s ORDER BY ah.Season_ID DESC", (name,)),
        "win_streaks": ("SELECT * FROM longestwinstreaks WHERE Fighter_Name = %s", (name,)),
        "loss_streaks": ("SELECT * FROM longestlosingstreaks WHERE Fighter_Name = %s", (name,)),
        "active_win": ("SELECT Win_Streak FROM allwinstreaks WHERE Fighter_Name = %s AND Active_Win_Streak = 'Active'", (name,)),
        "active_loss": ("SELECT Losing_Streak FROM alllosingsteaks WHERE Fighter_Name = %s AND Active_Losing_Streak = 'Active'", (name,)),
        "current_titles": ("SELECT Championship_Name FROM CurrentChampions WHERE Fighter_Name = %s", (name,)),
        "champ_by_champ": ("SELECT * FROM champfightstatsbychampionship WHERE Fighter_Name = %s", (name,)),
        "holistic": ("SELECT * FROM holistic_view WHERE Fighter_Name = %s ORDER BY Season", (name,)),
        "triple_crown": ("SELECT * FROM triplecrown", ()),
        "major_winner": ("SELECT * FROM majorwinner WHERE Fighter_Name = %s", (name,)),
    }

    def run_query(key_query):
        """Execute one accolade query and fall back to an empty list on failure."""
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(run_query, queries.items()))

    return {key: data for key, data in results}


def get_advanced_analytics(name):
    """Return advanced analytics datasets for a single fighter page."""
    queries = {
        "running_stats": (
            "SELECT Season, Month, Week, Fight_ID, Decision, "
            "Season_Running_Wins, Season_Running_Losses, "
            "Career_Running_Wins, Career_Running_Losses, "
            "Season_Running_Win_Pct, Career_Running_Win_Pct "
            "FROM CareerRunningStats WHERE Fighter_Name = %s "
            "ORDER BY Season, Month, Week, Fight_ID",
            (name,),
        ),
        "by_opponent": ("SELECT * FROM CareerStatsByOpponent WHERE Fighter_Name = %s ORDER BY (Wins + Losses) DESC", (name,)),
        "all_win_streaks": ("SELECT * FROM allwinstreaks WHERE Fighter_Name = %s ORDER BY Season_Started, Month_Started, Week_Started", (name,)),
        "all_loss_streaks": ("SELECT * FROM alllosingsteaks WHERE Fighter_Name = %s ORDER BY Season_Started, Month_Started, Week_Started", (name,)),
        "elo_history": (
            "SELECT e.result_id, e.fight_id, f.Season_ID AS season, f.Month AS month, f.Week AS week, "
            "ROUND(e.elo_before, 2) AS elo_before, ROUND(e.elo_after, 2) AS elo_after, "
            "ROUND(e.elo_after - e.elo_before, 2) AS elo_change "
            "FROM Elo e JOIN Fight f ON e.fight_id = f.Fight_ID "
            "WHERE e.fighter_name = %s ORDER BY f.Season_ID, f.Month, f.Week, f.Fight_ID",
            (name,),
        ),
    }

    def run_query(key_query):
        """Execute one advanced-analytics query and fall back to an empty list on failure."""
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run_query, queries.items()))

    return {key: data for key, data in results}


def get_fighter_elo_history(name):
    """Return chronological Elo history points for a single fighter."""
    return select_view_dicts(
        """
        SELECT
            e.result_id,
            e.fight_id,
            f.Season_ID AS season,
            f.Month AS month,
            f.Week AS week,
            ROUND(e.elo_before, 2) AS elo_before,
            ROUND(e.elo_after,  2) AS elo_after,
            ROUND(e.elo_after - e.elo_before, 2) AS elo_change
        FROM Elo e
        JOIN Fight f ON e.fight_id = f.Fight_ID
        WHERE e.fighter_name = %s
        ORDER BY f.Season_ID, f.Month, f.Week, f.Fight_ID
        """,
        (name,),
    )

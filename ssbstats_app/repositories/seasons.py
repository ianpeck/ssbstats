from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories.base import select_list, select_view_dicts


def get_all_seasons():
    """Return every season identifier in ascending order."""
    return select_list("SELECT DISTINCT Season FROM CareerStatsBySeason ORDER BY Season", 0)


def get_season_summary(season):
    """Return the grouped payloads needed to render a season detail page."""
    queries = {
        "rankings": ("SELECT * FROM CareerStatsBySeason WHERE Season = %s", (season,)),
        "awards": ("SELECT ah.Fighter_Name, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Season_ID = %s ORDER BY a.Award_Name", (season,)),
        "holistic": ("SELECT * FROM holistic_view WHERE Season = %s", (season,)),
        "champ_history": ("SELECT * FROM ChampionshipHistory WHERE Season_Won <= %s AND (Season_Lost IS NULL OR Season_Lost >= %s) ORDER BY Championship_Name, Season_Won, Month_Won", (season, season)),
    }

    def run_query(key_query):
        """Execute one season-summary query and fall back to an empty list on failure."""
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run_query, queries.items()))

    return {key: data for key, data in results}


def get_season_awards(season):
    """Return season awards keyed by lowercase fighter name."""
    rows = select_view_dicts(
        "SELECT ah.Fighter_Name, a.Award_Name "
        "FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID "
        "WHERE ah.Season_ID = %s ORDER BY a.Award_Name",
        (season,),
    )
    result = {}
    for row in rows:
        result.setdefault((row["Fighter_Name"] or "").lower().strip(), []).append(row["Award_Name"])
    return result

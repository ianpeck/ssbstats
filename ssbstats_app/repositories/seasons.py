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
        "champ_history": (
            """
            SELECT h.*,
                   -- Inaugural champions were awarded a new title and defended it in its first-ever
                   -- fight, so they held it during the month they're recorded as winning it.
                   EXISTS (
                       SELECT 1 FROM Results r
                       JOIN Fight f ON f.Fight_ID = r.Fight_ID
                       JOIN Championship c ON c.Championship_ID = f.Championship_ID
                       WHERE c.Championship_Name = h.Championship_Name AND r.Fighter_Name = h.Fighter_Name
                         AND r.DefendingIndicator = 'y' AND f.Season_ID = h.Season_Won AND f.Month = h.Month_Won
                         AND f.Fight_ID = (SELECT MIN(f2.Fight_ID) FROM Fight f2 WHERE f2.Championship_ID = c.Championship_ID)
                   ) AS inaugural
            FROM ChampionshipHistory h
            WHERE h.Season_Won <= %s AND (h.Season_Lost IS NULL OR h.Season_Lost >= %s)
            ORDER BY h.Championship_Name, h.Season_Won, h.Month_Won
            """,
            (season, season),
        ),
        "facts": (
            """
            SELECT s.Game AS game, COUNT(DISTINCT f.Fight_ID) AS fights,
                   COUNT(DISTINCT CASE WHEN f.PPV_Name IS NOT NULL THEN CONCAT(f.Month, '|', f.PPV_Name) END) AS ppvs,
                   MAX(f.Month) AS last_month,
                   -- New reigns this season (tag partners count once), leaving out the yearly
                   -- Smash Bros. trophy and inaugural champions, who were awarded a new title
                   -- (they're the defending champion in its first-ever fight).
                   (SELECT COUNT(*) FROM (
                        SELECT DISTINCT h.Championship_Name, h.Season_Won, h.Month_Won, h.Season_Lost, h.Month_Lost
                        FROM ChampionshipHistory h
                        WHERE h.Season_Won = %s AND h.Championship_Name <> 'Smash Bros.'
                          AND NOT EXISTS (
                              SELECT 1 FROM FightLog d
                              WHERE d.Fight_ID = (SELECT MIN(x.Fight_ID) FROM FightLog x WHERE x.Championship_Name = h.Championship_Name)
                                AND d.Fighter_Name = h.Fighter_Name AND d.DefendingIndicator = 'y'
                                AND d.Season = h.Season_Won AND d.Month = h.Month_Won)
                   ) t) AS title_changes
            FROM Season s LEFT JOIN FightLog f ON f.Season = s.Season_ID
            WHERE s.Season_ID = %s
            GROUP BY s.Game
            """,
            (season, season),
        ),
        "calendar": ("SELECT DISTINCT Month, PPV_Name FROM FightLog WHERE Season = %s AND PPV_Name IS NOT NULL ORDER BY Month", (season,)),
        "cashins": ("SELECT Month, PPV_Name, Championship_Name, Fight_Winner_Name, Fight_Winner, Fight_Loser_Name FROM cashins WHERE Season_ID = %s ORDER BY Month", (season,)),
    }

    def run_query(key_query):
        """Execute one season-summary query and fall back to an empty list on failure."""
        key, (query, params) = key_query
        try:
            return key, select_view_dicts(query, params)
        except Exception:
            return key, []

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
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

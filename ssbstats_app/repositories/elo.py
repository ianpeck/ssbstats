from ssbstats_app.repositories.base import nk, select_view_dicts


def get_elo_leaderboard():
    """Return current, average, and peak Elo values for every fighter."""
    return select_view_dicts(
        """
        SELECT
            e.fighter_name,
            e.elo_after AS current_elo,
            ROUND(e.elo_after - 1500, 1) AS elo_vs_start,
            COUNT(*) AS fights_counted,
            SUM(e.elo_after > e.elo_before) AS elo_wins,
            SUM(e.elo_after < e.elo_before) AS elo_losses,
            RANK() OVER (ORDER BY e.elo_after DESC) AS elo_rank
        FROM Elo e
        INNER JOIN (
            SELECT fighter_name, MAX(fight_id) AS last_fight_id
            FROM Elo
            GROUP BY fighter_name
        ) latest ON e.fighter_name = latest.fighter_name
               AND e.fight_id = latest.last_fight_id
        GROUP BY e.fighter_name, e.elo_after
        ORDER BY e.elo_after DESC
        """
    )


def get_elo_for_leaderboard():
    """Return Elo leaderboard metrics keyed by lowercase fighter name."""
    rows = select_view_dicts(
        """
        SELECT
            fighter_name,
            ROUND(MAX(CASE WHEN fight_id = last_fight THEN elo_after END), 1) AS current_elo,
            ROUND(AVG(elo_after), 1) AS avg_elo,
            ROUND(MAX(elo_after), 1) AS peak_elo
        FROM (
            SELECT e.*, MAX(e.fight_id) OVER (PARTITION BY e.fighter_name) AS last_fight
            FROM Elo e
        ) t
        GROUP BY fighter_name
        """
    )
    return {nk(row["fighter_name"]): row for row in rows}


def get_elo_for_leaderboard_by_season(season):
    """Return season-scoped Elo metrics keyed by lowercase fighter name."""
    rows = select_view_dicts(
        """
        SELECT
            e.fighter_name,
            ROUND(MAX(e.elo_after), 1) AS peak_season_elo,
            ROUND(AVG(e.elo_after), 1) AS avg_elo,
            ROUND(MAX(CASE WHEN e.fight_id = last_fight.max_fight_id THEN e.elo_after END), 1) AS season_end_elo
        FROM Elo e
        JOIN Fight f ON e.fight_id = f.Fight_ID
        JOIN (
            SELECT e2.fighter_name, MAX(e2.fight_id) AS max_fight_id
            FROM Elo e2
            JOIN Fight f2 ON e2.fight_id = f2.Fight_ID
            WHERE f2.Season_ID = %s
            GROUP BY e2.fighter_name
        ) last_fight ON e.fighter_name = last_fight.fighter_name
        WHERE f.Season_ID = %s
        GROUP BY e.fighter_name
        """,
        (season, season),
    )
    return {nk(row["fighter_name"]): row for row in rows}


def get_elo_alltime_ranking(min_fights=50):
    """Return all-time Elo rankings for fighters meeting a minimum fight threshold."""
    return select_view_dicts(
        """
        SELECT
            fighter_name,
            ROUND(AVG(elo_after), 1) AS avg_elo,
            ROUND(MAX(elo_after), 1) AS peak_elo,
            ROUND(MIN(elo_after), 1) AS floor_elo,
            COUNT(*) AS fights_counted,
            RANK() OVER (ORDER BY AVG(elo_after) DESC) AS alltime_rank
        FROM Elo
        GROUP BY fighter_name
        HAVING fights_counted >= %s
        ORDER BY avg_elo DESC
        """,
        (min_fights,),
    )

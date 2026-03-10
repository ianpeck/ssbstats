from ssbstats_app.repositories.base import select_view_dicts


def get_fight_rows(fight_id):
    """Return all FightLog rows for one fight."""
    return select_view_dicts(
        """
        SELECT *
        FROM FightLog
        WHERE Fight_ID = %s
        ORDER BY Decision DESC, Fighter_Name
        """,
        (fight_id,),
    )


def get_elo_rows_for_fight(fight_id):
    """Return Elo before/after rows for one fight."""
    return select_view_dicts(
        """
        SELECT fighter_name, ROUND(elo_before, 2) AS elo_before, ROUND(elo_after, 2) AS elo_after
        FROM Elo
        WHERE fight_id = %s
        """,
        (fight_id,),
    )


def get_prior_rows_for_fighters(fighter_names, season, month, week, fight_id):
    """Return all prior FightLog rows for the provided fighters before this fight."""
    if not fighter_names:
        return []
    placeholders = ", ".join(["%s"] * len(fighter_names))
    sql = f"""
        SELECT *
        FROM FightLog
        WHERE Fighter_Name IN ({placeholders})
          AND (
            Season < %s
            OR (Season = %s AND Month < %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) < %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) = %s AND Fight_ID < %s)
          )
        ORDER BY Season, Month, COALESCE(Week, 99), Fight_ID, Fighter_Name
    """
    params = list(fighter_names) + [
        season,
        season,
        month,
        season,
        month,
        week,
        season,
        month,
        week,
        fight_id,
    ]
    return select_view_dicts(sql, params)


def get_prior_common_fight_rows(fighter1, fighter2, season, month, week, fight_id):
    """Return all prior fight rows for fights where both named fighters appeared."""
    return select_view_dicts(
        """
        SELECT fl.*
        FROM FightLog fl
        INNER JOIN (
            SELECT Fight_ID
            FROM FightLog
            WHERE Fighter_Name IN (%s, %s)
              AND (
                Season < %s
                OR (Season = %s AND Month < %s)
                OR (Season = %s AND Month = %s AND COALESCE(Week, 99) < %s)
                OR (Season = %s AND Month = %s AND COALESCE(Week, 99) = %s AND Fight_ID < %s)
              )
            GROUP BY Fight_ID
            HAVING COUNT(DISTINCT Fighter_Name) = 2
        ) ids ON fl.Fight_ID = ids.Fight_ID
        ORDER BY fl.Season, fl.Month, COALESCE(fl.Week, 99), fl.Fight_ID, fl.Fighter_Name
        """,
        (
            fighter1,
            fighter2,
            season,
            season,
            month,
            season,
            month,
            week,
            season,
            month,
            week,
            fight_id,
        ),
    )


def get_prev_next_fight_ids(season, month, week, fight_id):
    """Return the previous and next fight ids in chronological order."""
    prev_row = select_view_dicts(
        """
        SELECT Fight_ID
        FROM FightLog
        WHERE
            Season < %s
            OR (Season = %s AND Month < %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) < %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) = %s AND Fight_ID < %s)
        GROUP BY Fight_ID
        ORDER BY Season DESC, Month DESC, COALESCE(Week, 99) DESC, Fight_ID DESC
        LIMIT 1
        """,
        (season, season, month, season, month, week, season, month, week, fight_id),
    )
    next_row = select_view_dicts(
        """
        SELECT Fight_ID
        FROM FightLog
        WHERE
            Season > %s
            OR (Season = %s AND Month > %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) > %s)
            OR (Season = %s AND Month = %s AND COALESCE(Week, 99) = %s AND Fight_ID > %s)
        GROUP BY Fight_ID
        ORDER BY Season ASC, Month ASC, COALESCE(Week, 99) ASC, Fight_ID ASC
        LIMIT 1
        """,
        (season, season, month, season, month, week, season, month, week, fight_id),
    )
    return {
        "previous_fight_id": prev_row[0]["Fight_ID"] if prev_row else None,
        "next_fight_id": next_row[0]["Fight_ID"] if next_row else None,
    }

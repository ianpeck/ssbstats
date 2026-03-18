from ssbstats_app.repositories.base import select_view_dicts


def get_championship_history_alltime():
    """Return all championship history rows ordered by when reigns started."""
    return select_view_dicts("SELECT * FROM ChampionshipHistory ORDER BY Championship_Name, Season_Won, Month_Won")


def get_current_fight_date():
    """Return the most recent season and month present in FightLog."""
    rows = select_view_dicts("SELECT Season, Month FROM FightLog ORDER BY Season DESC, Month DESC LIMIT 1")
    if rows:
        return int(rows[0].get("Season") or 1), int(rows[0].get("Month") or 1)
    return 1, 1


def get_all_ppvs():
    """Return aggregated PPV history rows for the events page."""
    return select_view_dicts(
        "SELECT PPV_Name, Season, Month, "
        "COUNT(DISTINCT Fight_ID) as fight_count, "
        "COUNT(DISTINCT CASE WHEN Championship_Name IS NOT NULL AND Championship_Name != '' THEN Fight_ID END) as title_fights, "
        "MAX(Location_Name) as Location_Name "
        "FROM FightLog "
        "WHERE PPV_Name IS NOT NULL AND PPV_Name != '' "
        "GROUP BY PPV_Name, Season, Month "
        "ORDER BY Season DESC, Month DESC"
    )


def get_event_summary(ppv_name):
    """Return one aggregated summary row for an all-time PPV event."""
    rows = select_view_dicts(
        """
        SELECT
            fl.PPV_Name,
            MIN(fl.Season) AS first_season,
            MIN(CASE WHEN fl.Season = first_season_ref.first_season THEN fl.Month END) AS first_month,
            MAX(fl.Season) AS last_season,
            MAX(CASE WHEN fl.Season = last_season_ref.last_season THEN fl.Month END) AS last_month,
            COUNT(DISTINCT fl.Fight_ID) AS fight_count,
            COUNT(DISTINCT fl.Fighter_Name) AS unique_fighters,
            COUNT(DISTINCT CASE WHEN fl.Championship_Name IS NOT NULL AND fl.Championship_Name != '' THEN fl.Fight_ID END) AS title_fights,
            COUNT(DISTINCT CASE WHEN fl.Contender_Indicator IS NOT NULL AND fl.Contender_Indicator NOT IN ('', 'N', '0') THEN fl.Fight_ID END) AS contender_fights,
            COUNT(DISTINCT CONCAT(fl.Season, '-', fl.Month)) AS editions_count
        FROM FightLog fl
        JOIN (SELECT %s AS ppv_name, MIN(Season) AS first_season FROM FightLog WHERE PPV_Name = %s) first_season_ref
        JOIN (SELECT %s AS ppv_name, MAX(Season) AS last_season FROM FightLog WHERE PPV_Name = %s) last_season_ref
        WHERE fl.PPV_Name = %s
        GROUP BY fl.PPV_Name
        """,
        (ppv_name, ppv_name, ppv_name, ppv_name, ppv_name),
    )
    return rows[0] if rows else None


def get_event_fighter_records(ppv_name):
    """Return all-time fighter records for one PPV event."""
    return select_view_dicts(
        """
        SELECT
            Fighter_Name,
            SUM(CASE WHEN Decision = 'W' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN Decision = 'L' THEN 1 ELSE 0 END) AS losses
        FROM FightLog
        WHERE PPV_Name = %s
        GROUP BY Fighter_Name
        HAVING wins + losses > 0
        ORDER BY wins + losses DESC, wins DESC, Fighter_Name
        """,
        (ppv_name,),
    )


def get_event_biggest_upsets(ppv_name, limit=8):
    """Return the largest singles upsets for an all-time PPV event."""
    return select_view_dicts(
        """
        SELECT
            fw.Fight_ID,
            fw.Season,
            fw.Month,
            fw.Fighter_Name AS winner_name,
            fl.Fighter_Name AS loser_name,
            fw.Description,
            fw.Championship_Name,
            fw.Location_Name,
            ROUND(ew.elo_before, 1) AS winner_elo_before,
            ROUND(ew.elo_after, 1) AS winner_elo_after,
            ROUND(el.elo_before, 1) AS loser_elo_before,
            ROUND(el.elo_before - ew.elo_before, 1) AS upset_gap,
            ROUND(ew.elo_after - ew.elo_before, 1) AS elo_swing
        FROM FightLog fw
        JOIN FightLog fl
            ON fw.Fight_ID = fl.Fight_ID
           AND fw.Decision = 'W'
           AND fl.Decision = 'L'
        JOIN Elo ew ON ew.result_id = fw.Result_ID
        JOIN Elo el ON el.result_id = fl.Result_ID
        JOIN (
            SELECT Fight_ID
            FROM FightLog
            WHERE PPV_Name = %s
            GROUP BY Fight_ID
            HAVING COUNT(*) = 2
               AND SUM(CASE WHEN Decision = 'W' THEN 1 ELSE 0 END) = 1
               AND SUM(CASE WHEN Decision = 'L' THEN 1 ELSE 0 END) = 1
        ) singles ON singles.Fight_ID = fw.Fight_ID
        WHERE fw.PPV_Name = %s
        ORDER BY upset_gap DESC, elo_swing DESC, fw.Fight_ID DESC
        LIMIT %s
        """,
        (ppv_name, ppv_name, limit),
    )


def get_event_editions(ppv_name):
    """Return every edition of a PPV event across league history."""
    return select_view_dicts(
        """
        SELECT
            PPV_Name,
            Season,
            Month,
            MAX(Location_Name) AS Location_Name,
            COUNT(DISTINCT Fight_ID) AS fight_count,
            COUNT(DISTINCT CASE WHEN Championship_Name IS NOT NULL AND Championship_Name != '' THEN Fight_ID END) AS title_fights
        FROM FightLog
        WHERE PPV_Name = %s
        GROUP BY PPV_Name, Season, Month
        ORDER BY Season DESC, Month DESC
        """,
        (ppv_name,),
    )


def get_championship_history_by_season_alltime():
    """Return championship history grouped at the season level."""
    return select_view_dicts("SELECT * FROM ChampionshipHistoryBySeason ORDER BY Championship_Name, Season, Month_Won, Fighter_Name")

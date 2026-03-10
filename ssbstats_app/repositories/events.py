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


def get_championship_history_by_season_alltime():
    """Return championship history grouped at the season level."""
    return select_view_dicts("SELECT * FROM ChampionshipHistoryBySeason ORDER BY Championship_Name, Season, Month_Won, Fighter_Name")

from ssbstats_app.repositories.base import select_view_dicts


def get_stage_index():
    """Every stage with its usage totals, unused stages included."""
    return select_view_dicts(
        """
        SELECT
            l.Location_Name,
            l.Location_GameSeries,
            l.Location_Origin,
            COALESCE(s.fights, 0) AS fights,
            COALESCE(s.title_fights, 0) AS title_fights,
            COALESCE(s.ppv_fights, 0) AS ppv_fights,
            COALESCE(s.fighters, 0) AS fighters,
            s.first_season,
            s.last_season
        FROM Location l
        LEFT JOIN (
            SELECT
                Location_Name,
                COUNT(DISTINCT Fight_ID) AS fights,
                COUNT(DISTINCT CASE WHEN Championship_Name IS NOT NULL AND Championship_Name != '' THEN Fight_ID END) AS title_fights,
                COUNT(DISTINCT CASE WHEN PPV_Name IS NOT NULL AND PPV_Name != '' THEN Fight_ID END) AS ppv_fights,
                COUNT(DISTINCT Fighter_Name) AS fighters,
                MIN(Season) AS first_season,
                MAX(Season) AS last_season
            FROM FightLog
            GROUP BY Location_Name
        ) s ON s.Location_Name = l.Location_Name
        ORDER BY fights DESC, l.Location_Name
        """
    )


def get_stage_kings():
    """The fighter with the most wins on each stage."""
    return select_view_dicts(
        """
        SELECT Location_Name, Fighter_Name, Wins, Losses
        FROM (
            SELECT Location_Name, Fighter_Name, Wins, Losses,
                   ROW_NUMBER() OVER (PARTITION BY Location_Name ORDER BY Wins DESC, Losses, Fighter_Name) AS rn
            FROM CareerStatsByLocation
        ) ranked
        WHERE rn = 1
        """
    )


def get_stage_fighter_records(location):
    """Every fighter's record on one stage."""
    return select_view_dicts(
        """
        SELECT Fighter_Name, Wins AS wins, Losses AS losses
        FROM CareerStatsByLocation
        WHERE Location_Name = %s
        """,
        (location,),
    )


def get_stage_biggest_upsets(location, limit=5):
    """The largest singles upsets on one stage, by the Elo gap the winner overcame."""
    return select_view_dicts(
        """
        SELECT
            fw.Fight_ID,
            fw.Season,
            fw.Month,
            fw.Fighter_Name AS winner_name,
            fl.Fighter_Name AS loser_name,
            fw.Championship_Name,
            ROUND(el.elo_before - ew.elo_before, 1) AS upset_gap
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
            WHERE Location_Name = %s
            GROUP BY Fight_ID
            HAVING COUNT(*) = 2
               AND SUM(CASE WHEN Decision = 'W' THEN 1 ELSE 0 END) = 1
               AND SUM(CASE WHEN Decision = 'L' THEN 1 ELSE 0 END) = 1
        ) singles ON singles.Fight_ID = fw.Fight_ID
        WHERE fw.Location_Name = %s AND el.elo_before > ew.elo_before
        ORDER BY upset_gap DESC, fw.Fight_ID DESC
        LIMIT %s
        """,
        (location, location, limit),
    )


def get_stage_rivalries(location, limit=5):
    """The singles matchups fought most often on one stage."""
    return select_view_dicts(
        """
        SELECT
            LEAST(w.Fighter_Name, l.Fighter_Name) AS fighter_a,
            GREATEST(w.Fighter_Name, l.Fighter_Name) AS fighter_b,
            COUNT(*) AS fights,
            SUM(CASE WHEN w.Fighter_Name = LEAST(w.Fighter_Name, l.Fighter_Name) THEN 1 ELSE 0 END) AS a_wins,
            MAX(w.Fight_ID) AS last_fight_id
        FROM FightLog w
        JOIN FightLog l
            ON l.Fight_ID = w.Fight_ID
           AND w.Decision = 'W'
           AND l.Decision = 'L'
        JOIN (
            SELECT Fight_ID
            FROM FightLog
            WHERE Location_Name = %s
            GROUP BY Fight_ID
            HAVING COUNT(*) = 2
        ) singles ON singles.Fight_ID = w.Fight_ID
        GROUP BY fighter_a, fighter_b
        HAVING fights >= 2
        ORDER BY fights DESC, last_fight_id DESC
        LIMIT %s
        """,
        (location, limit),
    )

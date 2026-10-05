"""Championship lineages for the Championships page and the per-title history pages."""

from ssbstats_app.repositories.base import select_view_dicts


def get_championships():
    """Every championship with its tier."""
    return select_view_dicts("SELECT Championship_ID, Championship_Name, championship_tier AS tier FROM Championship ORDER BY Championship_ID")


def get_reigns():
    """Every reign in lineage order, with whether it was an inaugural (awarded) reign and the
    fight where the title was won (NULL for inaugural reigns and other awarded titles)."""
    return select_view_dicts(
        """
        WITH title_wins AS (
            SELECT Fighter_Name, Championship_Name, Season, Month, Week, Fight_ID, PPV_Name, Location_Name, Description,
                   ROW_NUMBER() OVER (
                       PARTITION BY Fighter_Name, Championship_Name, Season, Month ORDER BY Week, Fight_ID
                   ) AS rn
            FROM FightLog
            WHERE Decision = 'w' AND DefendingIndicator IS NULL AND Championship_Name IS NOT NULL
        )
        SELECT h.Fighter_Name, h.Championship_Name, h.Season_Won, h.Month_Won, h.Season_Lost, h.Month_Lost, h.months_held,
               -- Inaugural champions were awarded a new title and defended it in its first-ever fight.
               EXISTS (
                   SELECT 1 FROM Results r
                   JOIN Fight f ON f.Fight_ID = r.Fight_ID
                   JOIN Championship c ON c.Championship_ID = f.Championship_ID
                   WHERE c.Championship_Name = h.Championship_Name AND r.Fighter_Name = h.Fighter_Name
                     AND r.DefendingIndicator = 'y' AND f.Season_ID = h.Season_Won AND f.Month = h.Month_Won
                     AND f.Fight_ID = (SELECT MIN(f2.Fight_ID) FROM Fight f2 WHERE f2.Championship_ID = c.Championship_ID)
               ) AS inaugural,
               w.Fight_ID AS won_fight_id, w.Week AS won_week, w.PPV_Name AS won_ppv,
               w.Location_Name AS won_location, w.Description AS won_fight_type
        FROM ChampionshipHistory h
        LEFT JOIN title_wins w
               ON w.rn = 1 AND w.Fighter_Name = h.Fighter_Name AND w.Championship_Name = h.Championship_Name
              AND w.Season = h.Season_Won AND w.Month = h.Month_Won
        -- Within a month, the reign that ended first came first (e.g. a cash-in, then a rematch).
        ORDER BY h.Championship_Name, h.Season_Won, h.Month_Won, h.Season_Lost IS NULL, h.Season_Lost, h.Month_Lost, h.Fighter_Name
        """
    )


def get_bracket_defenses():
    """Tournament and Scramble rounds won by a sitting champion. No title is attached to these rounds
    (only the final carries a belt), but losing any of them costs the champion the title, so each one
    counts as a defense of the major title the fighter held at the time."""
    return select_view_dicts(
        """
        SELECT Fight_ID, Season, Month, Fighter_Name, Description
        FROM FightLog
        WHERE DefendingIndicator = 'y' AND Decision = 'w' AND Championship_Name IS NULL
        """
    )

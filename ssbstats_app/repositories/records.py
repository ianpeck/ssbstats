"""All-time league records for the Record Book page.

Every query returns a short, ranked list (one row per fighter, pair or reign)
rather than raw history, so the page can show a holder plus a few runners-up.
"""

from ssbstats_app.repositories.base import select_view_dicts


# Fights with exactly one winner and one loser: the only fights where an Elo gap
# or a series record between two fighters means something.
_SINGLES = """
    SELECT Fight_ID FROM FightLog
    GROUP BY Fight_ID
    HAVING COUNT(*) = 2 AND SUM(Decision = 'w') = 1 AND SUM(Decision = 'l') = 1
"""

# Latest (season, month) with a fight, used to measure reigns that are still going.
_NOW = "(SELECT Season, MAX(Month) AS Month FROM FightLog WHERE Season = (SELECT MAX(Season) FROM FightLog) GROUP BY Season)"


def get_latest_month():
    rows = select_view_dicts(f"SELECT Season, Month FROM {_NOW} now")
    return rows[0] if rows else {"Season": 0, "Month": 0}


def get_longest_win_streaks(limit):
    """Each fighter's best win streak (the most recent one when tied)."""
    return select_view_dicts(
        """
        SELECT Fighter_Name, Win_Streak AS value, Active_Win_Streak = 'Active' AS active,
               Season_Started, Month_Started, Season_Ended, Month_Ended
        FROM (
            SELECT s.*, ROW_NUMBER() OVER (
                PARTITION BY Fighter_Name ORDER BY Win_Streak DESC, Season_Started DESC, Month_Started DESC
            ) AS rn
            FROM allwinstreaks s
        ) best
        WHERE rn = 1
        ORDER BY value DESC, Season_Started, Month_Started
        LIMIT %s
        """,
        (limit,),
    )


def get_peak_elo(limit):
    """Each fighter's highest Elo rating, and when they first reached it."""
    return select_view_dicts(
        """
        SELECT Fighter_Name, ROUND(elo_after) AS value, Season, Month, Fight_ID
        FROM (
            SELECT f.Fighter_Name, e.elo_after, f.Season, f.Month, f.Fight_ID,
                   ROW_NUMBER() OVER (PARTITION BY f.Fighter_Name ORDER BY e.elo_after DESC, f.Fight_ID) AS rn
            FROM Elo e JOIN FightLog f ON f.Result_ID = e.result_id
        ) best
        WHERE rn = 1
        ORDER BY value DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_best_seasons(limit, min_fights=15):
    """Highest single-season win percentage (minimum decisions so a 3-0 start doesn't count)."""
    return select_view_dicts(
        """
        SELECT Fighter_Name, Season, Wins, Losses, Wins / (Wins + Losses) AS pct
        FROM CareerStatsBySeason
        WHERE Wins + Losses >= %s
        ORDER BY pct DESC, Wins DESC
        LIMIT %s
        """,
        (min_fights, limit),
    )


def get_most_season_wins(limit):
    return select_view_dicts(
        """
        SELECT Fighter_Name, Season, Wins AS value, Losses
        FROM CareerStatsBySeason
        ORDER BY Wins DESC, Losses
        LIMIT %s
        """,
        (limit,),
    )


def get_most_title_reigns(limit):
    return select_view_dicts(
        """
        SELECT Fighter_Name, COUNT(*) AS value,
               COUNT(DISTINCT Championship_Name) AS belts,
               SUM(Championship_Tier = 'Major') AS majors
        FROM ChampionshipHistory
        WHERE Championship_Name != 'Smash Bros.'  -- a once-a-year trophy, not a title reign
        GROUP BY Fighter_Name
        ORDER BY value DESC, majors DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_most_title_defenses(limit):
    return select_view_dicts(
        """
        SELECT Fighter_Name, COUNT(*) AS value,
               SUM(Championship_Name LIKE 'Unified Tag%%') AS tag
        FROM FightLog
        WHERE DefendingIndicator = 'y' AND Decision = 'w'
          -- Bracket wins count: a champion who enters a Tournament or Scramble defends the
          -- title in every round. The Smash Bros. trophy is won yearly, not defended.
          AND COALESCE(Championship_Name, '') != 'Smash Bros.'
        GROUP BY Fighter_Name
        ORDER BY value DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_longest_singles_reigns(limit):
    """Longest singles title reigns, counting reigns still in progress up to the latest month."""
    return select_view_dicts(
        f"""
        SELECT h.Fighter_Name, h.Championship_Name, h.Season_Won, h.Month_Won, h.Season_Lost, h.Month_Lost,
               h.Season_Lost IS NULL AS active,
               COALESCE(h.months_held, (now.Season - h.Season_Won) * 12 + now.Month - h.Month_Won) AS value
        FROM ChampionshipHistory h CROSS JOIN {_NOW} now
        WHERE h.Championship_Name NOT LIKE 'Unified Tag%%' AND h.Championship_Name != 'Smash Bros.'
        ORDER BY value DESC, h.Season_Won
        LIMIT %s
        """,
        (limit,),
    )


def get_longest_tag_reigns(limit):
    """Longest tag title reigns, one row per team reign."""
    return select_view_dicts(
        f"""
        SELECT GROUP_CONCAT(h.Fighter_Name ORDER BY h.Fighter_Name SEPARATOR '|') AS team,
               h.Season_Won, h.Month_Won, h.Season_Lost, h.Month_Lost,
               MAX(h.Season_Lost IS NULL) AS active,
               MAX(COALESCE(h.months_held, (now.Season - h.Season_Won) * 12 + now.Month - h.Month_Won)) AS value
        FROM ChampionshipHistory h CROSS JOIN {_NOW} now
        WHERE h.Championship_Name LIKE 'Unified Tag%%'
        GROUP BY h.Season_Won, h.Month_Won, h.Season_Lost, h.Month_Lost
        ORDER BY value DESC, h.Season_Won
        LIMIT %s
        """,
        (limit,),
    )


def get_most_ppv_wins(limit):
    return select_view_dicts(
        """
        SELECT Fighter_Name, SUM(Decision = 'w') AS value, SUM(Decision = 'l') AS losses
        FROM FightLog
        WHERE PPV_Name IS NOT NULL
        GROUP BY Fighter_Name
        ORDER BY value DESC, losses
        LIMIT %s
        """,
        (limit,),
    )


def get_event_trophies(limit):
    """Wins of the league's marquee events, per fighter, with the breakdown."""
    return select_view_dicts(
        """
        SELECT Fighter_Name,
               SUM(Won_Royal_Rumble IS NOT NULL) AS rumble,
               SUM(Won_Money_In_The_Bank IS NOT NULL) AS mitb,
               SUM(Won_Tournament IS NOT NULL) AS tournament,
               SUM(Won_Scramble IS NOT NULL) AS scramble,
               SUM(Won_Smash_Series IS NOT NULL) AS smash_series,
               SUM(Won_Smash_Bros IS NOT NULL) AS smash_bros,
               SUM(Won_Royal_Rumble IS NOT NULL) + SUM(Won_Money_In_The_Bank IS NOT NULL)
                 + SUM(Won_Tournament IS NOT NULL) + SUM(Won_Scramble IS NOT NULL)
                 + SUM(Won_Smash_Series IS NOT NULL) + SUM(Won_Smash_Bros IS NOT NULL) AS value
        FROM holistic_view
        GROUP BY Fighter_Name
        HAVING value > 0
        ORDER BY value DESC, tournament DESC, Fighter_Name
        LIMIT %s
        """,
        (limit,),
    )


def get_superstars_of_the_year():
    return select_view_dicts(
        """
        SELECT ah.Season_ID AS Season, ah.Fighter_Name
        FROM AwardHistory ah JOIN Award a ON a.Award_ID = ah.Award_ID
        WHERE a.Award_Name = 'Superstar of the Year'
        ORDER BY ah.Season_ID
        """
    )


def get_rivalries(limit, min_meetings=1, order="meetings"):
    """One-on-one series between two fighters.

    order="meetings" ranks the most-played series; order="lopsided" ranks the most
    one-sided series among those with at least min_meetings.
    """
    order_by = (
        "meetings DESC, ABS(wins1 - wins2)"
        if order == "meetings"
        else "GREATEST(wins1, wins2) / meetings DESC, meetings DESC"
    )
    return select_view_dicts(
        f"""
        WITH singles AS ({_SINGLES}),
        pairs AS (
            SELECT a.Fight_ID, a.Fighter_Name AS f1, b.Fighter_Name AS f2, a.Decision = 'w' AS f1_won
            FROM singles s
            JOIN FightLog a ON a.Fight_ID = s.Fight_ID
            JOIN FightLog b ON b.Fight_ID = s.Fight_ID AND a.Fighter_Name < b.Fighter_Name
        )
        SELECT f1, f2, COUNT(*) AS meetings, SUM(f1_won) AS wins1, COUNT(*) - SUM(f1_won) AS wins2,
               MAX(Fight_ID) AS last_fight
        FROM pairs
        GROUP BY f1, f2
        HAVING meetings >= %s
        ORDER BY {order_by}
        LIMIT %s
        """,
        (min_meetings, limit),
    )


def get_biggest_upsets(limit):
    """One-on-one wins over the highest-rated opponents relative to the winner's own Elo."""
    return select_view_dicts(
        f"""
        WITH singles AS ({_SINGLES})
        SELECT fw.Fight_ID, fw.Season, fw.Month, fw.Fighter_Name AS winner, fl.Fighter_Name AS loser,
               fw.PPV_Name, fw.Championship_Name,
               ROUND(ew.elo_before) AS winner_elo, ROUND(el.elo_before) AS loser_elo,
               ROUND(el.elo_before - ew.elo_before) AS value
        FROM singles s
        JOIN FightLog fw ON fw.Fight_ID = s.Fight_ID AND fw.Decision = 'w'
        JOIN FightLog fl ON fl.Fight_ID = s.Fight_ID AND fl.Decision = 'l'
        JOIN Elo ew ON ew.result_id = fw.Result_ID
        JOIN Elo el ON el.result_id = fl.Result_ID
        ORDER BY value DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_first_title_wins():
    """Each fighter's first reign in every major title and in the minor and tag tiers, with the
    fight where they won it (NULL when the reign has no title-winning fight on record)."""
    return select_view_dicts(
        """
        WITH firsts AS (
            SELECT h.Fighter_Name, c.championship_tier AS tier, h.Championship_Name, h.Season_Won, h.Month_Won,
                   ROW_NUMBER() OVER (
                       PARTITION BY h.Fighter_Name,
                                    CASE WHEN c.championship_tier = 'Major' THEN h.Championship_Name ELSE c.championship_tier END
                       ORDER BY h.Season_Won, h.Month_Won
                   ) AS rn
            FROM ChampionshipHistory h
            JOIN Championship c ON c.Championship_Name = h.Championship_Name
            WHERE c.championship_tier IN ('Major', 'Minor', 'Tag')
        ),
        title_wins AS (
            SELECT Fighter_Name, Championship_Name, Season, Month, Fight_ID, PPV_Name, Location_Name,
                   ROW_NUMBER() OVER (
                       PARTITION BY Fighter_Name, Championship_Name, Season, Month ORDER BY Week, Fight_ID
                   ) AS rn
            FROM FightLog
            WHERE Decision = 'w' AND DefendingIndicator IS NULL AND Championship_Name IS NOT NULL
        )
        SELECT f.Fighter_Name, f.tier, f.Championship_Name, f.Season_Won, f.Month_Won,
               w.Fight_ID, w.PPV_Name, w.Location_Name
        FROM firsts f
        LEFT JOIN title_wins w
               ON w.rn = 1 AND w.Fighter_Name = f.Fighter_Name AND w.Championship_Name = f.Championship_Name
              AND w.Season = f.Season_Won AND w.Month = f.Month_Won
        WHERE f.rn = 1
        ORDER BY f.Fighter_Name, f.Season_Won, f.Month_Won
        """
    )


def get_fighter_stage_records(min_fights):
    """Every fighter's record on every stage they've fought on at least min_fights times."""
    return select_view_dicts(
        """
        SELECT Fighter_Name, Location_Name, Wins, Losses
        FROM CareerStatsByLocation
        WHERE Wins + Losses >= %s
        """,
        (min_fights,),
    )

from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories.base import h2h_query_sql, select_view_dicts, select_view_row


def get_comparison_data(f1, f2):
    """Return the raw datasets required for the fighter comparison page."""
    queries = {
        "f1_career": ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (f1,)),
        "f2_career": ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (f2,)),
        "f1_season": ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s ORDER BY Season", (f1,)),
        "f2_season": ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s ORDER BY Season", (f2,)),
        "f1_holistic": ("SELECT * FROM holistic_view WHERE Fighter_Name = %s ORDER BY Season", (f1,)),
        "f2_holistic": ("SELECT * FROM holistic_view WHERE Fighter_Name = %s ORDER BY Season", (f2,)),
        "f1_running": ("SELECT Season, Month, Week, Fight_ID, Decision, Career_Running_Win_Pct FROM CareerRunningStats WHERE Fighter_Name = %s ORDER BY Season, Month, Week, Fight_ID", (f1,)),
        "f2_running": ("SELECT Season, Month, Week, Fight_ID, Decision, Career_Running_Win_Pct FROM CareerRunningStats WHERE Fighter_Name = %s ORDER BY Season, Month, Week, Fight_ID", (f2,)),
        "f1_elo_history": ("SELECT e.fight_id, f.Season_ID AS season, f.Month AS month, f.Week AS week, ROUND(e.elo_before, 2) AS elo_before, ROUND(e.elo_after, 2) AS elo_after FROM Elo e JOIN Fight f ON e.fight_id = f.Fight_ID WHERE e.fighter_name = %s ORDER BY f.Season_ID, f.Month, f.Week, f.Fight_ID", (f1,)),
        "f2_elo_history": ("SELECT e.fight_id, f.Season_ID AS season, f.Month AS month, f.Week AS week, ROUND(e.elo_before, 2) AS elo_before, ROUND(e.elo_after, 2) AS elo_after FROM Elo e JOIN Fight f ON e.fight_id = f.Fight_ID WHERE e.fighter_name = %s ORDER BY f.Season_ID, f.Month, f.Week, f.Fight_ID", (f2,)),
        "f1_champs": ("SELECT COUNT(DISTINCT Championship_Name) AS total FROM ChampionshipHistory WHERE Fighter_Name = %s", (f1,)),
        "f2_champs": ("SELECT COUNT(DISTINCT Championship_Name) AS total FROM ChampionshipHistory WHERE Fighter_Name = %s", (f2,)),
        "f1_champ_stats": ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (f1,)),
        "f2_champ_stats": ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (f2,)),
        "f1_awards": ("SELECT ah.Season_ID, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Fighter_Name = %s ORDER BY ah.Season_ID", (f1,)),
        "f2_awards": ("SELECT ah.Season_ID, a.Award_Name FROM AwardHistory ah JOIN Award a ON ah.Award_ID = a.Award_ID WHERE ah.Fighter_Name = %s ORDER BY ah.Season_ID", (f2,)),
        "fights": ("""SELECT fl.Season, fl.Month, fl.Week, fl.Fight_ID, fl.Fighter_Name, fl.Decision, fl.Championship_Name, fl.Description, fl.PPV_Name, fl.Location_Name FROM FightLog fl WHERE fl.Fight_ID IN (SELECT r1.Fight_ID FROM Results r1 JOIN Results r2 ON r1.Fight_ID = r2.Fight_ID AND r1.Fighter_Name = %s AND r2.Fighter_Name = %s) AND fl.Fighter_Name IN (%s, %s) ORDER BY fl.Season DESC, fl.Month DESC, COALESCE(fl.Week, 99) DESC, fl.Fight_ID DESC""", (f1, f2, f1, f2)),
        "roster_max_months": ("""SELECT MAX(total_major) AS max_major, MAX(total_title) AS max_title FROM (SELECT Fighter_Name, SUM(COALESCE(Months_With_Major, 0)) AS total_major, SUM(COALESCE(Months_With_Title, 0)) AS total_title FROM holistic_view GROUP BY Fighter_Name) t""", ()),
        "roster_max_wr": ("""SELECT MAX(CAST(REPLACE(`Win Percentage`, '%', '') AS DECIMAL(5,2))) AS max_wr FROM careerstats""", ()),
        "roster_max_ev": ("""SELECT MAX(ev_count) AS max_ev FROM (SELECT Fighter_Name, MAX(CASE WHEN Won_Tournament        IS NOT NULL AND Won_Tournament        != '' THEN 1 ELSE 0 END) + MAX(CASE WHEN Won_Royal_Rumble      IS NOT NULL AND Won_Royal_Rumble      != '' THEN 1 ELSE 0 END) + MAX(CASE WHEN Won_Scramble          IS NOT NULL AND Won_Scramble          != '' THEN 1 ELSE 0 END) + MAX(CASE WHEN Won_Smash_Series      IS NOT NULL AND Won_Smash_Series      != '' THEN 1 ELSE 0 END) + MAX(CASE WHEN Won_Money_In_The_Bank IS NOT NULL AND Won_Money_In_The_Bank != '' THEN 1 ELSE 0 END) + MAX(CASE WHEN Won_Smash_Bros        IS NOT NULL AND Won_Smash_Bros        != '' THEN 1 ELSE 0 END) AS ev_count FROM holistic_view GROUP BY Fighter_Name) t""", ()),
        "roster_max_champs": ("""SELECT MAX(cnt) AS max_tc FROM (SELECT COUNT(DISTINCT Championship_Name) AS cnt FROM ChampionshipHistory GROUP BY Fighter_Name) t""", ()),
        "season_roster_max_holistic": ("""SELECT MAX(CAST(REPLACE(Win_Percentage, '%', '') AS DECIMAL(5,2))) AS max_wr, MAX(COALESCE(Months_With_Major, 0)) AS max_major, MAX(COALESCE(Months_With_Title, 0)) AS max_title, MAX(COALESCE(Title_Count, 0)) AS max_tc, MAX((CASE WHEN Won_Tournament IS NOT NULL AND Won_Tournament != '' THEN 1 ELSE 0 END) + (CASE WHEN Won_Royal_Rumble IS NOT NULL AND Won_Royal_Rumble != '' THEN 1 ELSE 0 END) + (CASE WHEN Won_Scramble IS NOT NULL AND Won_Scramble != '' THEN 1 ELSE 0 END) + (CASE WHEN Won_Smash_Series IS NOT NULL AND Won_Smash_Series != '' THEN 1 ELSE 0 END) + (CASE WHEN Won_Money_In_The_Bank IS NOT NULL AND Won_Money_In_The_Bank != '' THEN 1 ELSE 0 END) + (CASE WHEN Won_Smash_Bros IS NOT NULL AND Won_Smash_Bros != '' THEN 1 ELSE 0 END)) AS max_ev FROM holistic_view""", ()),
    }

    with ThreadPoolExecutor(max_workers=20) as pool:
        view_futures = {key: pool.submit(select_view_dicts, query, params) for key, (query, params) in queries.items()}
        h2h_future = pool.submit(h2h_query_sql, "CALL SmashBros.headtohead(%s, %s)", (f1, f2))

    result = {}
    for key, future in view_futures.items():
        try:
            result[key] = future.result()
        except Exception:
            result[key] = []
    try:
        result["h2h"] = h2h_future.result()
    except Exception:
        result["h2h"] = [
            {"Fighter": f1, "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
            {"Fighter": f2, "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
        ]
    return result


def get_h2h_data(fighter1, fighter2, filters):
    """Return head-to-head data across the supported filter dimensions."""
    map_name = filters.get("map", "")
    match_type = filters.get("matchType", "")
    season = filters.get("season", "")
    month = filters.get("month", "")
    ppv = filters.get("ppv", "")
    brand = filters.get("brand", "")

    individual_queries = [
        ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s AND Location_Name = %s", (fighter1, map_name)),
        ("SELECT * FROM CareerStatsByLocation WHERE Fighter_Name = %s AND Location_Name = %s", (fighter2, map_name)),
        ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s AND FightType = %s", (fighter1, match_type)),
        ("SELECT * FROM CareerStatsByFightType WHERE Fighter_Name = %s AND FightType = %s", (fighter2, match_type)),
        ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM champfightstats WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s AND PPV = %s", (fighter1, ppv)),
        ("SELECT * FROM CareerStatsByPPV WHERE Fighter_Name = %s AND PPV = %s", (fighter2, ppv)),
        ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM defendingtitle WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (fighter1,)),
        ("SELECT * FROM careerstats WHERE Fighter_Name = %s", (fighter2,)),
        ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s AND Season = %s", (fighter1, season)),
        ("SELECT * FROM CareerStatsBySeason WHERE Fighter_Name = %s AND Season = %s", (fighter2, season)),
        ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s AND Brand = %s", (fighter1, brand)),
        ("SELECT * FROM CareerStatsByBrand WHERE Fighter_Name = %s AND Brand = %s", (fighter2, brand)),
    ]

    stored_procedures = [
        ("call SmashBros.headtohead(%s, %s)", (fighter1, fighter2)),
        ("call SmashBros.headtoheadLocation(%s, %s, %s)", (fighter1, fighter2, map_name)),
        ("call SmashBros.headtoheadFightType(%s, %s, %s)", (fighter1, fighter2, match_type)),
        ("call SmashBros.headtoheadSeason(%s, %s, %s)", (fighter1, fighter2, season)),
        ("call SmashBros.headtoheadMonth(%s, %s, %s)", (fighter1, fighter2, month)),
        ("call SmashBros.headtoheadChamp(%s, %s)", (fighter1, fighter2)),
        ("call SmashBros.headtoheadPPV(%s, %s, %s)", (fighter1, fighter2, ppv)),
    ]

    def run_individual(query_params):
        """Execute one individual fighter stat query for the H2H payload."""
        try:
            return select_view_row(query_params[0], query_params[1])
        except Exception:
            return None

    def run_h2h(query_params):
        """Execute one stored-procedure H2H query with a safe empty fallback."""
        try:
            return h2h_query_sql(query_params[0], query_params[1])
        except Exception:
            return [
                {"Fighter": "", "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
                {"Fighter": "", "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
            ]

    with ThreadPoolExecutor(max_workers=23) as pool:
        individual_results = list(pool.map(run_individual, individual_queries))
        h2h_results = list(pool.map(run_h2h, stored_procedures))

    row_labels = [
        "at Location",
        "for Match Type",
        "in Championship matches",
        "at PPV",
        "when Defending a Title",
        "Total Record",
        "Season Record",
        "On Brand",
    ]
    f1_individual = []
    f2_individual = []
    for i, data in enumerate(individual_results):
        entry = {"wins": "0", "losses": "0", "wl_pct": "0.00%"}
        if data and len(data) > 0:
            row = data[0]
            entry = {"wins": str(row[-3]), "losses": str(row[-2]), "wl_pct": str(row[-1])}
        if i % 2 == 0:
            f1_individual.append(entry)
        else:
            f2_individual.append(entry)

    h2h_labels = [
        "Vs. Other Fighter (Total)",
        "Vs. Other Fighter (At Location)",
        "Vs. Other Fighter (Match Type)",
        "Vs. Other Fighter (in Season)",
        "Vs. Other Fighter (in Month)",
        "Vs. Other Fighter (for Championship)",
        "Vs. Other Fighter (at PPV)",
    ]
    f1_h2h = []
    f2_h2h = []
    for pair in h2h_results:
        f1_h2h.append({"wins": pair[0].get("Wins", "0"), "losses": pair[0].get("Losses", "0"), "wl_pct": pair[0].get("W/L %", "0.00%")})
        f2_h2h.append({"wins": pair[1].get("Wins", "0"), "losses": pair[1].get("Losses", "0"), "wl_pct": pair[1].get("W/L %", "0.00%")})

    return {
        "fighter1": {
            "name": fighter1,
            "h2h": [{"label": h2h_labels[i], **f1_h2h[i]} for i in range(len(f1_h2h))],
            "individual": [{"label": row_labels[i], **f1_individual[i]} for i in range(len(f1_individual))],
        },
        "fighter2": {
            "name": fighter2,
            "h2h": [{"label": h2h_labels[i], **f2_h2h[i]} for i in range(len(f2_h2h))],
            "individual": [{"label": row_labels[i], **f2_individual[i]} for i in range(len(f2_individual))],
        },
    }

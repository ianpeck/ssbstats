from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories import comparisons, events, fighters, fights, leaderboards, lookups, power, seasons
from ssbstats_app.utils import fighter_to_filename, normalize_champ_name, serialize_value, stage_to_filename


def build_index_payload():
    """Build the roster card payload used by the landing page."""
    fighters = get_fighters()
    current_champs = lookups.get_current_champions()
    return [
        {
            "name": fighter,
            "filename": fighter_to_filename(fighter),
            "titles": [normalize_champ_name(title) for title in current_champs.get(fighter.lower(), [])],
        }
        for fighter in fighters
    ]


def get_fighters():
    """Return the canonical fighter list used across the app."""
    from ssbstats_app.services.content import get_autocomplete_data

    return get_autocomplete_data("fighters")


def get_fights_page_filters():
    """Collect the filter option payload for the fight log page."""
    from ssbstats_app.services.content import get_autocomplete_data

    return {
        "seasons": seasons.get_all_seasons(),
        "fight_types": get_autocomplete_data("fight_types"),
        "locations": get_autocomplete_data("locations"),
        "ppvs": get_autocomplete_data("ppvs"),
        "championships": get_autocomplete_data("championships"),
        "brands": get_autocomplete_data("brands"),
        "fighters": get_autocomplete_data("fighters"),
    }


def get_head_to_head(fighter1, fighter2, filters):
    """Return head-to-head results with image metadata added."""
    results = comparisons.get_h2h_data(fighter1, fighter2, filters)
    results["fighter1"]["image"] = fighter_to_filename(fighter1) + ".png"
    results["fighter2"]["image"] = fighter_to_filename(fighter2) + ".png"
    results["stage_image"] = stage_to_filename(filters["map"]) + ".png" if filters["map"] else ""
    return results


def get_fighter_profile_payload(name):
    """Assemble the full fighter profile JSON payload."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        career_future = pool.submit(fighters.get_fighter_career_stats, name)
        accolades_future = pool.submit(fighters.get_fighter_accolades, name)
        ps_season_future = pool.submit(power.get_all_season_power_scores)
        ps_career_future = pool.submit(power.get_career_power_scores)
        stats = career_future.result()
        accolades_raw = accolades_future.result()
        ps_all = ps_season_future.result()
        ps_career = ps_career_future.result()

    result = {"name": name, "image": fighter_to_filename(name) + ".png"}

    if stats.get("career"):
        row = stats["career"][0]
        result["career"] = {"wins": row[1] if len(row) > 1 else 0, "losses": row[2] if len(row) > 2 else 0, "win_pct": str(row[3]) if len(row) > 3 else "0.00%"}
    else:
        result["career"] = {"wins": 0, "losses": 0, "win_pct": "0.00%"}

    result["by_season"] = [
        {"season": str(row[1]) if len(row) > 1 else "", "wins": row[2] if len(row) > 2 else 0, "losses": row[3] if len(row) > 3 else 0, "win_pct": str(row[4]) if len(row) > 4 else "0.00%"}
        for row in stats.get("by_season", [])
    ]
    result["by_location"] = [
        {"location": str(row[1]) if len(row) > 1 else "", "wins": row[2] if len(row) > 2 else 0, "losses": row[3] if len(row) > 3 else 0, "win_pct": str(row[4]) if len(row) > 4 else "0.00%"}
        for row in stats.get("by_location", [])
    ]
    result["by_fight_type"] = [
        {"type": str(row[1]) if len(row) > 1 else "", "wins": row[2] if len(row) > 2 else 0, "losses": row[3] if len(row) > 3 else 0, "win_pct": str(row[4]) if len(row) > 4 else "0.00%"}
        for row in stats.get("by_fight_type", [])
    ]
    result["by_brand"] = [
        {"brand": str(row[1]) if len(row) > 1 else "", "wins": row[2] if len(row) > 2 else 0, "losses": row[3] if len(row) > 3 else 0, "win_pct": str(row[4]) if len(row) > 4 else "0.00%"}
        for row in stats.get("by_brand", [])
    ]
    result["by_ppv"] = [
        {"ppv": str(row[1]) if len(row) > 1 else "", "wins": row[2] if len(row) > 2 else 0, "losses": row[3] if len(row) > 3 else 0, "win_pct": str(row[4]) if len(row) > 4 else "0.00%"}
        for row in stats.get("by_ppv", [])
    ]
    result["championship"] = [
        {"wins": row[-3] if len(row) >= 3 else 0, "losses": row[-2] if len(row) >= 2 else 0, "win_pct": str(row[-1]) if len(row) >= 1 else "0.00%"}
        for row in stats.get("championship", [])
    ]
    result["defending_title"] = [
        {"wins": row[-3] if len(row) >= 3 else 0, "losses": row[-2] if len(row) >= 2 else 0, "win_pct": str(row[-1]) if len(row) >= 1 else "0.00%"}
        for row in stats.get("defending_title", [])
    ]
    result["current_titles"] = [normalize_champ_name(row["Championship_Name"]) for row in accolades_raw.get("current_titles", [])]

    tc_rows = accolades_raw.get("triple_crown", [])
    result["triple_crown"] = any(any(str(value) == name for value in row.values() if value is not None) for row in tc_rows)

    mw_rows = accolades_raw.get("major_winner", [])
    if mw_rows:
        mw_row = mw_rows[0]
        try:
            mw_count = sum(1 for key, value in mw_row.items() if key.lower() != "fighter_name" and int(value or 0) > 0)
        except (TypeError, ValueError):
            mw_count = 0
        result["major_winner"] = "super" if mw_count >= 3 else ("major" if mw_count >= 2 else None)
    else:
        result["major_winner"] = None

    result["accolades"] = {
        key: [{field: serialize_value(value) for field, value in row.items()} for row in rows]
        for key, rows in accolades_raw.items()
    }
    for row in result["accolades"].get("champ_reigns", []):
        row["Championship_Name"] = normalize_champ_name(row.get("Championship_Name"))
    for row in result["accolades"].get("champ_by_champ", []):
        row["Championship_Name"] = normalize_champ_name(row.get("Championship_Name"))
    for row in result["accolades"].get("holistic", []):
        if row.get("Titles_Held"):
            row["Titles_Held"] = normalize_champ_name(row["Titles_Held"])

    nk = name.lower()
    result["career_power_score"] = ps_career.get(nk, {})
    result["power_scores_by_season"] = {str(season): ps_all[season][nk] for season in sorted(ps_all.keys()) if nk in ps_all[season]}
    return result


def get_fighter_advanced_payload(name):
    """Assemble advanced analytics payloads for a fighter."""
    raw = fighters.get_advanced_analytics(name)
    return {
        "running_stats": [
            {
                "season": row.get("Season"),
                "month": row.get("Month"),
                "week": row.get("Week"),
                "fight_id": row.get("Fight_ID"),
                "decision": row.get("Decision"),
                "career_wins": int(row.get("Career_Running_Wins") or 0),
                "career_losses": int(row.get("Career_Running_Losses") or 0),
                "season_win_pct": str(row.get("Season_Running_Win_Pct") or "0.00%"),
                "career_win_pct": str(row.get("Career_Running_Win_Pct") or "0.00%"),
            }
            for row in raw.get("running_stats", [])
        ],
        "by_opponent": [
            {
                "opponent": row.get("Opponent", ""),
                "wins": int(row.get("Wins") or 0),
                "losses": int(row.get("Losses") or 0),
                "win_pct": str(row.get("Win Percentage") or "0.00%"),
            }
            for row in raw.get("by_opponent", [])
        ],
        "all_win_streaks": [{key: serialize_value(value) for key, value in row.items()} for row in raw.get("all_win_streaks", [])],
        "all_loss_streaks": [{key: serialize_value(value) for key, value in row.items()} for row in raw.get("all_loss_streaks", [])],
        "elo_history": [{key: serialize_value(value) for key, value in row.items()} for row in raw.get("elo_history", [])],
    }


def get_leaderboard_payload(season):
    """Return leaderboard rows with awards and title badges merged in."""
    if season:
        season_int = int(season)
        with ThreadPoolExecutor(max_workers=2) as pool:
            lb_future = pool.submit(leaderboards.get_leaderboard_by_season, season_int)
            awards_future = pool.submit(seasons.get_season_awards, season_int)
            fighters = lb_future.result()
            awards = awards_future.result()
        for fighter in fighters:
            fighter["season_awards"] = awards.get((fighter.get("name") or "").lower(), [])
    else:
        fighters = leaderboards.get_leaderboard()

    current_champs = lookups.get_current_champions()
    for fighter in fighters:
        fighter["titles"] = [normalize_champ_name(title) for title in current_champs.get((fighter.get("name") or "").lower(), [])]
    return fighters


def get_season_payload(season_id):
    """Assemble the payload for a single season detail page."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        summary_future = pool.submit(seasons.get_season_summary, season_id)
        ps_future = pool.submit(power.get_season_power_scores, season_id)
        data = summary_future.result()
        ps_map = ps_future.result()

    rankings = data.get("rankings", [])
    canonical_map = lookups.get_canonical_name_map()

    def parse_pct(row):
        """Extract the first percentage-like field from a ranking row."""
        value = next((row[key] for key in row if "pct" in key.lower() or "%" in key.lower() or "percentage" in key.lower()), 0)
        try:
            return float(str(value).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    rankings.sort(key=parse_pct, reverse=True)
    for row in rankings:
        name = row.get("Fighter_Name") or row.get("fighter_name") or ""
        row["Fighter_Name"] = canonical_map.get(name.lower(), name)
        ps = ps_map.get(row["Fighter_Name"].lower(), {})
        row["power_score"] = ps.get("power_score")
        row["power_rank"] = ps.get("power_rank")
    data["rankings"] = rankings

    for row in data.get("holistic", []):
        if row.get("Titles_Held"):
            row["Titles_Held"] = normalize_champ_name(row["Titles_Held"])
    for row in data.get("champ_history", []):
        if row.get("Championship_Name"):
            row["Championship_Name"] = normalize_champ_name(row["Championship_Name"])

    return {
        key: [{field: serialize_value(value) for field, value in row.items()} for row in rows]
        for key, rows in data.items()
    }


def get_fight_log_payload(filters, page):
    """Return serialized fight log rows for the requested filter set."""
    fights_data = fights.get_fight_log(filters, page=page)
    result = []
    for fight in fights_data:
        serialized_fight = {key: serialize_value(value) for key, value in fight.items() if key != "fighters"}
        serialized_fight["fighters"] = [{key: serialize_value(value) for key, value in fighter.items()} for fighter in fight["fighters"]]
        result.append(serialized_fight)
    return result


def get_compare_payload(f1, f2):
    """Assemble the full fighter-vs-fighter comparison payload."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        raw_future = pool.submit(comparisons.get_comparison_data, f1, f2)
        ps_future = pool.submit(power.get_all_season_power_scores)
        ps_career_future = pool.submit(power.get_career_power_scores)
        raw = raw_future.result()
        ps_all = ps_future.result()
        ps_career = ps_career_future.result()

    def career(rows):
        """Convert career rows into the compare page's summary shape."""
        if not rows:
            return {"wins": 0, "losses": 0, "win_pct": "0.00%"}
        row = rows[0]
        return {"wins": serialize_value(row.get("Wins", 0)), "losses": serialize_value(row.get("Losses", 0)), "win_pct": str(row.get("Win Percentage", "0.00%"))}

    def by_season(rows):
        """Convert season rows into the compare page's season-summary shape."""
        return [{"season": str(row.get("Season", "")), "wins": serialize_value(row.get("Wins", 0)), "losses": serialize_value(row.get("Losses", 0)), "win_pct": str(row.get("Win Percentage", "0.00%"))} for row in rows]

    def holistic(rows):
        """Normalize holistic rows for compare-page rendering."""
        output = []
        for row in rows:
            serialized = {key: serialize_value(value) for key, value in row.items()}
            if serialized.get("Titles_Held"):
                serialized["Titles_Held"] = normalize_champ_name(serialized["Titles_Held"])
            output.append(serialized)
        return output

    def running(rows):
        """Convert running win-rate rows for the momentum chart."""
        return [{"season": row.get("Season"), "month": row.get("Month"), "week": row.get("Week"), "decision": row.get("Decision"), "career_win_pct": str(row.get("Career_Running_Win_Pct", "0.00%"))} for row in rows]

    def unique_champs(rows):
        """Extract the distinct championship count from an aggregate query."""
        return int(rows[0].get("total", 0)) if rows else 0

    def champ_stats(rows):
        """Convert championship rows into the compare page's summary shape."""
        if not rows:
            return {"wins": 0, "losses": 0, "win_pct": "0.00%"}
        row = rows[0]
        return {"wins": serialize_value(row.get("Wins", 0)), "losses": serialize_value(row.get("Losses", 0)), "win_pct": str(row.get("Win Percentage", "0.00%"))}

    def awards(rows):
        """Convert award rows into a small season/name structure."""
        return [{"season": int(row.get("Season_ID", 0)), "name": str(row.get("Award_Name", ""))} for row in rows]

    def elo_history(rows):
        """Convert Elo history rows into the compare page's chart shape."""
        return [{"fight_id": int(row.get("fight_id", 0)), "season": int(row.get("season", 0)), "month": int(row.get("month", 0)), "week": row.get("week"), "elo_before": float(row.get("elo_before", 0)), "elo_after": float(row.get("elo_after", 0))} for row in rows]

    h2h = raw.get("h2h", [])
    fights = [{key: serialize_value(value) for key, value in row.items()} for row in raw.get("fights", [])]

    def fighter_payload(name, prefix):
        """Assemble one side of the compare payload from the raw query bundle."""
        nk = name.lower()
        return {
            "name": name,
            "image": fighter_to_filename(name) + ".png",
            "career": career(raw.get(f"{prefix}_career", [])),
            "by_season": by_season(raw.get(f"{prefix}_season", [])),
            "holistic": holistic(raw.get(f"{prefix}_holistic", [])),
            "running": running(raw.get(f"{prefix}_running", [])),
            "unique_champs": unique_champs(raw.get(f"{prefix}_champs", [])),
            "champ_stats": champ_stats(raw.get(f"{prefix}_champ_stats", [])),
            "awards": awards(raw.get(f"{prefix}_awards", [])),
            "elo_history": elo_history(raw.get(f"{prefix}_elo_history", [])),
            "h2h_wins": int(h2h[0 if prefix == "f1" else 1].get("Wins", 0)) if len(h2h) > 1 else 0,
            "h2h_losses": int(h2h[0 if prefix == "f1" else 1].get("Losses", 0)) if len(h2h) > 1 else 0,
            "career_power_score": ps_career.get(nk, {}),
            "power_scores_by_season": {str(season): ps_all[season][nk] for season in sorted(ps_all.keys()) if nk in ps_all[season]},
        }

    months = (raw.get("roster_max_months") or [{}])[0]
    wr_row = (raw.get("roster_max_wr") or [{}])[0]
    ev_row = (raw.get("roster_max_ev") or [{}])[0]
    tc_row = (raw.get("roster_max_champs") or [{}])[0]
    season_row = (raw.get("season_roster_max_holistic") or [{}])[0]

    return {
        "fighter1": fighter_payload(f1, "f1"),
        "fighter2": fighter_payload(f2, "f2"),
        "fights_between": fights,
        "roster_maxes": {
            "max_wr": float(serialize_value(wr_row.get("max_wr")) or 100),
            "max_major": float(serialize_value(months.get("max_major")) or 1),
            "max_title": float(serialize_value(months.get("max_title")) or 1),
            "max_ev": int(serialize_value(ev_row.get("max_ev")) or 1),
            "max_champs": int(serialize_value(tc_row.get("max_tc")) or 1),
        },
        "season_roster_maxes": {
            "max_wr": float(serialize_value(season_row.get("max_wr")) or 100),
            "max_major": float(serialize_value(season_row.get("max_major")) or 1),
            "max_title": float(serialize_value(season_row.get("max_title")) or 1),
            "max_ev": int(serialize_value(season_row.get("max_ev")) or 1),
            "max_champs": int(serialize_value(season_row.get("max_tc")) or 1),
        },
    }


def get_championships_payload():
    """Return championship history rows plus current date markers."""
    rows = events.get_championship_history_alltime()
    for row in rows:
        if row.get("Championship_Name"):
            row["Championship_Name"] = normalize_champ_name(row["Championship_Name"])
    current = events.get_current_fight_date()
    return {
        "rows": [{key: serialize_value(value) for key, value in row.items()} for row in rows],
        "current_season": current[0],
        "current_month": current[1],
    }


def get_events_payload():
    """Return serialized PPV and event history rows."""
    rows = events.get_all_ppvs()
    return [{key: serialize_value(value) for key, value in row.items()} for row in rows]

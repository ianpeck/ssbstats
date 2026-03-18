from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.repositories import comparisons, elo, events, fight_detail, fighters, fights, leaderboards, lookups, power, seasons
from ssbstats_app.utils import event_to_slug, fighter_to_filename, normalize_champ_name, serialize_value, stage_to_filename


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
        latest_season = lookups.get_latest_season()
        show_titles = season_int == latest_season
    else:
        fighters = leaderboards.get_leaderboard()
        show_titles = True

    if show_titles:
        current_champs = lookups.get_current_champions()
        for fighter in fighters:
            fighter["titles"] = [normalize_champ_name(title) for title in current_champs.get((fighter.get("name") or "").lower(), [])]
    return fighters


def get_season_payload(season_id):
    """Assemble the payload for a single season detail page."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        summary_future = pool.submit(seasons.get_season_summary, season_id)
        ps_future = pool.submit(power.get_season_power_scores, season_id)
        elo_future = pool.submit(elo.get_elo_for_leaderboard_by_season, season_id)
        data = summary_future.result()
        ps_map = ps_future.result()
        elo_map = elo_future.result()

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
        elo_row = elo_map.get(row["Fighter_Name"].lower().strip(), {})
        row["peak_season_elo"] = elo_row.get("peak_season_elo")
        row["avg_elo"] = elo_row.get("avg_elo")
        row["season_end_elo"] = elo_row.get("season_end_elo")
    data["rankings"] = rankings

    # Include current champions only for the latest season
    latest = lookups.get_latest_season()
    if season_id == latest:
        current_champs = lookups.get_current_champions()
        data["current_champions"] = [
            {"Fighter_Name": name, "Championship_Name": normalize_champ_name(title)}
            for name, titles in current_champs.items()
            for title in titles
        ]

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


def get_fight_detail_payload(fight_id):
    """Assemble the full payload for the dedicated fight detail page."""
    fight_rows = fight_detail.get_fight_rows(fight_id)
    if not fight_rows:
        return None

    base = fight_rows[0]
    season = int(base.get("Season") or 0)
    month = int(base.get("Month") or 0)
    week = int(base.get("Week") or 99)
    location = base.get("Location_Name")
    fight_type = base.get("Description")
    ppv = base.get("PPV_Name")
    championship = normalize_champ_name(base.get("Championship_Name")) if base.get("Championship_Name") else ""
    brand = base.get("Brand_Name")

    elo_rows = fight_detail.get_elo_rows_for_fight(fight_id)
    elo_by_name = {row.get("fighter_name", "").lower(): row for row in elo_rows}

    participants = []
    for row in fight_rows:
        name = row.get("Fighter_Name") or "?"
        elo = elo_by_name.get(name.lower(), {})
        participants.append(
            {
                "name": name,
                "filename": fighter_to_filename(name),
                "decision": str(row.get("Decision") or "").upper(),
                "match_result": serialize_value(row.get("Match_Result")),
                "seed": serialize_value(row.get("Seed")),
                "defending": str(row.get("DefendingIndicator") or "").upper() not in ("", "N", "0", "NONE"),
                "contender": str(row.get("Contender_Indicator") or "").upper() not in ("", "N", "0", "NONE"),
                "elo_before": serialize_value(elo.get("elo_before")),
                "elo_after": serialize_value(elo.get("elo_after")),
            }
        )

    winners = [participant for participant in participants if participant["decision"] == "W"]
    losers = [participant for participant in participants if participant["decision"] == "L"]
    fight_type_lower = (fight_type or "").lower()
    is_team = fight_type_lower in ("tag team", "handicap")
    is_singles = not is_team and len(participants) == 2
    layout = "tag" if is_team else ("singles" if is_singles else "multi")

    fighter_names = [participant["name"] for participant in participants]
    prior_rows = fight_detail.get_prior_rows_for_fighters(fighter_names, season, month, week, fight_id)
    prior_by_fighter = {}
    for row in prior_rows:
        prior_by_fighter.setdefault(row.get("Fighter_Name") or "", []).append(row)

    def record_from_rows(rows, predicate=None):
        """Count wins and losses from a list of fight rows."""
        wins = 0
        losses = 0
        for row in rows:
            if predicate and not predicate(row):
                continue
            decision = str(row.get("Decision") or "").upper()
            if decision == "W":
                wins += 1
            elif decision == "L":
                losses += 1
        return {"wins": wins, "losses": losses, "win_pct": f"{(wins / (wins + losses) * 100):.2f}%" if wins + losses else "0.00%"}

    def streak_from_rows(rows):
        """Return the active streak entering the fight from reverse chronological rows."""
        if not rows:
            return {"type": "none", "count": 0, "label": "No active streak"}
        ordered = list(rows)
        ordered.sort(key=lambda row: (row.get("Season") or 0, row.get("Month") or 0, row.get("Week") if row.get("Week") is not None else 99, row.get("Fight_ID") or 0), reverse=True)
        first = str(ordered[0].get("Decision") or "").upper()
        if first not in ("W", "L"):
            return {"type": "none", "count": 0, "label": "No active streak"}
        count = 0
        for row in ordered:
            if str(row.get("Decision") or "").upper() == first:
                count += 1
            else:
                break
        return {
            "type": "win" if first == "W" else "loss",
            "count": count,
            "label": f"{count}-fight {'win' if first == 'W' else 'loss'} streak",
        }

    def participant_context(participant):
        """Build the pre-fight snapshot card for a participant."""
        rows = prior_by_fighter.get(participant["name"], [])
        current_season = record_from_rows(rows, lambda row: int(row.get("Season") or 0) == season)
        at_location = record_from_rows(rows, lambda row: row.get("Location_Name") == location)
        by_type = record_from_rows(rows, lambda row: row.get("Description") == fight_type)
        at_ppv = record_from_rows(rows, lambda row: row.get("PPV_Name") == ppv)
        contextual_records = []
        if championship:
            championship_record = record_from_rows(
                rows,
                lambda row: normalize_champ_name(row.get("Championship_Name")) == championship if row.get("Championship_Name") else False,
            )
            contextual_records.append(
                {
                    "label": f"For {championship}",
                    "record": championship_record,
                }
            )
        if participant["contender"]:
            contender_record = record_from_rows(
                rows,
                lambda row: str(row.get("Contender_Indicator") or "").upper() not in ("", "N", "0", "NONE"),
            )
            contextual_records.append(
                {
                    "label": "#1 Contender Matches",
                    "record": contender_record,
                }
            )
        if participant["defending"]:
            defending_record = record_from_rows(
                rows,
                lambda row: str(row.get("DefendingIndicator") or "").upper() not in ("", "N", "0", "NONE"),
            )
            contextual_records.append(
                {
                    "label": "Title Defenses",
                    "record": defending_record,
                }
            )
        return {
            "name": participant["name"],
            "filename": participant["filename"],
            "career": record_from_rows(rows),
            "season": current_season,
            "location": at_location,
            "fight_type": by_type,
            "ppv": at_ppv,
            "streak": streak_from_rows(rows),
            "elo_before": participant.get("elo_before"),
            "status": (
                "Champion"
                if participant["defending"]
                else ("Contender" if championship or participant["contender"] else "Entrant")
            ),
            "contextual_records": contextual_records,
        }

    participant_cards = [participant_context(participant) for participant in participants]

    matchup_context = None
    if is_singles:
        f1 = participants[0]["name"]
        f2 = participants[1]["name"]
        common_rows = fight_detail.get_prior_common_fight_rows(f1, f2, season, month, week, fight_id)
        grouped_common = {}
        for row in common_rows:
            grouped_common.setdefault(row.get("Fight_ID"), []).append(row)
        direct_prior = []
        for rows in grouped_common.values():
            if len(rows) != 2:
                continue
            names = {rows[0].get("Fighter_Name"), rows[1].get("Fighter_Name")}
            decisions = {str(rows[0].get("Decision") or "").upper(), str(rows[1].get("Decision") or "").upper()}
            if names == {f1, f2} and decisions == {"W", "L"}:
                direct_prior.append(rows)

        wins1 = 0
        wins2 = 0
        for rows in direct_prior:
            for row in rows:
                if row.get("Fighter_Name") == f1 and str(row.get("Decision") or "").upper() == "W":
                    wins1 += 1
                if row.get("Fighter_Name") == f2 and str(row.get("Decision") or "").upper() == "W":
                    wins2 += 1

        def matchup_record(predicate=None):
            """Return the pre-fight matchup record for the two fighters under a specific filter."""
            record = {
                f1: {"wins": 0, "losses": 0},
                f2: {"wins": 0, "losses": 0},
            }
            for rows in direct_prior:
                if predicate and not any(predicate(row) for row in rows):
                    continue
                for row in rows:
                    name = row.get("Fighter_Name")
                    decision = str(row.get("Decision") or "").upper()
                    if name not in record or decision not in ("W", "L"):
                        continue
                    if decision == "W":
                        record[name]["wins"] += 1
                    else:
                        record[name]["losses"] += 1
            return record

        winner_name = winners[0]["name"] if len(winners) == 1 else None
        post_wins1 = wins1 + (1 if winner_name == f1 else 0)
        post_wins2 = wins2 + (1 if winner_name == f2 else 0)
        matchup_context = {
            "fighter1": f1,
            "fighter2": f2,
            "pre_h2h": {"fighter1_wins": wins1, "fighter2_wins": wins2, "total_fights": wins1 + wins2},
            "post_h2h": {"fighter1_wins": post_wins1, "fighter2_wins": post_wins2, "total_fights": post_wins1 + post_wins2},
            "location_record": matchup_record(lambda row: row.get("Location_Name") == location),
            "fight_type_record": matchup_record(lambda row: row.get("Description") == fight_type),
            "ppv_record": matchup_record(lambda row: row.get("PPV_Name") == ppv),
            "season_record": matchup_record(lambda row: int(row.get("Season") or 0) == season),
            "championship_record": matchup_record(
                lambda row: normalize_champ_name(row.get("Championship_Name")) == championship if row.get("Championship_Name") else False
            ) if championship else None,
        }

    insights = []
    if championship:
        defending_winners = [participant for participant in winners if participant["defending"]]
        defending_losers = [participant for participant in losers if participant["defending"]]
        if defending_losers and not defending_winners and winners:
            insights.append(f"{' & '.join(participant['name'] for participant in winners)} captured the {championship}.")
        elif defending_winners:
            insights.append(f"{' & '.join(participant['name'] for participant in defending_winners)} successfully defended the {championship}.")
    if is_singles and matchup_context and matchup_context["pre_h2h"]["total_fights"] == 0:
        insights.append("This was their first recorded singles meeting.")
    for participant in participants:
        if participant.get("elo_before") is not None and participant.get("elo_after") is not None:
            delta = round(float(participant["elo_after"]) - float(participant["elo_before"]), 2)
            if delta:
                sign = "+" if delta > 0 else ""
                insights.append(f"{participant['name']} moved {sign}{delta} Elo in this fight.")

    result_summary = _build_fight_result_summary(participants, winners, losers, fight_type, championship)
    navigation = fight_detail.get_prev_next_fight_ids(season, month, week, fight_id)

    return {
        "fight_id": fight_id,
        "season": season,
        "month": month,
        "week": None if week == 99 else week,
        "ppv": ppv,
        "location": location,
        "stage_image": stage_to_filename(location) + ".png" if location else "",
        "fight_type": fight_type,
        "championship": championship,
        "brand": brand,
        "participants": participant_cards,
        "participants_raw": participants,
        "winners": winners,
        "losers": losers,
        "layout": layout,
        "result_summary": result_summary,
        "matchup_context": matchup_context,
        "insights": insights,
        "navigation": navigation,
        "hero_title": _build_fight_hero_title(participants, winners, losers, fight_type, championship),
        "hero_subtitle": _build_fight_hero_subtitle(season, month, None if week == 99 else week, ppv, brand),
    }


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


def _build_fight_result_summary(participants, winners, losers, fight_type, championship=""):
    """Build a concise fight result string for the detail page."""
    fight_type_lower = (fight_type or "").lower()
    winner_names = " & ".join(participant["name"] for participant in winners) if winners else ""
    loser_names = " & ".join(participant["name"] for participant in losers) if losers else ""

    if championship and winner_names and loser_names:
        title_label = f"{championship} Title"
        defending_winners = [participant for participant in winners if participant.get("defending")]
        defending_losers = [participant for participant in losers if participant.get("defending")]
        if defending_winners:
            retain_verb = "retains" if len(defending_winners) == 1 else "retain"
            return f"{winner_names} {retain_verb} the {title_label}"
        if defending_losers:
            verb = "defeats" if len(winners) == 1 else "defeat"
            return f"{winner_names} {verb} {loser_names} for the {title_label}"
        if len(winners) == 1:
            return f"{winner_names} wins the {title_label}"
        return f"{winner_names} win the {title_label}"

    if fight_type_lower == "smash series" and winner_names:
        return f"{winner_names} win the Smash Series"

    if len(participants) == 2 and len(winners) == 1 and len(losers) == 1:
        result = winners[0].get("match_result")
        suffix = f" {result}" if result not in (None, "", "None") else ""
        return f"{winners[0]['name']} def. {losers[0]['name']}{suffix}"
    if fight_type_lower in ("tag team", "handicap"):
        winner_names = winner_names or "Winning team"
        loser_names = loser_names or "Opposing team"
        return f"{winner_names} def. {loser_names}"
    if winners:
        return f"{', '.join(participant['name'] for participant in winners)} won this {fight_type or 'fight'}."
    return f"{fight_type or 'Fight'} result recorded."


def _build_fight_hero_title(participants, winners, losers, fight_type, championship=""):
    """Build the page hero title based on match type and participants."""
    fight_type_lower = (fight_type or "").lower()
    winner_names = " & ".join(participant["name"] for participant in winners) if winners else ""
    loser_names = " & ".join(participant["name"] for participant in losers) if losers else ""

    if championship and winner_names:
        title_label = f"{championship} Title"
        defending_winners = [participant for participant in winners if participant.get("defending")]
        defending_losers = [participant for participant in losers if participant.get("defending")]
        if fight_type_lower == "cash in":
            if defending_winners:
                return f"{winner_names} Defends Against The Cash-In To Retain The {title_label}"
            if defending_losers:
                return f"{winner_names} Cashes In And Captures The {title_label}"
            if len(winners) == 1:
                return f"{winner_names} Wins The {title_label}"
            return f"{winner_names} Win The {title_label}"
        if defending_winners:
            verb = "Retains" if len(defending_winners) == 1 else "Retain"
            return f"{winner_names} {verb} The {title_label}"
        if defending_losers and loser_names:
            verb = "Defeats" if len(winners) == 1 else "Defeat"
            return f"{winner_names} {verb} {loser_names} For The {title_label}"
        if len(winners) == 1:
            return f"{winner_names} Wins The {title_label}"
        return f"{winner_names} Win The {title_label}"

    if fight_type_lower == "smash series" and winner_names:
        return f"{winner_names} Win The Smash Series"

    if len(participants) == 2:
        return f"{participants[0]['name']} vs. {participants[1]['name']}"
    if fight_type_lower in ("tag team", "handicap"):
        return f"{winner_names} vs. {loser_names}"
    if winners:
        return f"{winners[0]['name']} won the {fight_type or 'match'}"
    return fight_type or "Fight Detail"


def _build_fight_hero_subtitle(season, month, week, ppv, brand):
    """Build the compact chronology subtitle for the hero section."""
    parts = [f"Season {season}", f"Month {month}"]
    if week is not None:
        parts.append(f"Week {week}")
    if ppv:
        parts.append(ppv)
    if brand:
        parts.append(brand)
    return " · ".join(parts)


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
    payload = []
    for row in rows:
        serialized = {key: serialize_value(value) for key, value in row.items()}
        serialized["ppv_slug"] = event_to_slug(serialized.get("PPV_Name"))
        payload.append(serialized)
    return payload


def _event_weighted_win_pct(wins, losses, prior=0.5, strength=4):
    """Return a sample-aware weighted win percentage."""
    total = wins + losses
    if total <= 0:
        return 0.0
    return ((wins + (prior * strength)) / (total + strength)) * 100


def get_event_detail_payload(slug):
    """Assemble the analytics payload for one all-time PPV event page."""
    rows = get_events_payload()
    base = next((row for row in rows if row.get("ppv_slug") == slug), None)
    if not base:
        return None

    ppv_name = base.get("PPV_Name")
    summary = events.get_event_summary(ppv_name)
    if not summary:
        return None

    records_raw = events.get_event_fighter_records(ppv_name)
    upsets_raw = events.get_event_biggest_upsets(ppv_name)
    editions_raw = events.get_event_editions(ppv_name)
    fights_raw = fights.get_fight_log({"ppv": ppv_name}, page=1, per_page=200)

    fighter_records = []
    for row in records_raw:
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        total = wins + losses
        win_pct = (wins / total * 100) if total else 0.0
        fighter_records.append(
            {
                "fighter_name": row.get("Fighter_Name"),
                "filename": fighter_to_filename(row.get("Fighter_Name") or ""),
                "wins": wins,
                "losses": losses,
                "total": total,
                "win_pct": round(win_pct, 2),
                "weighted_win_pct": round(_event_weighted_win_pct(wins, losses), 2),
            }
        )

    qualified = [row for row in fighter_records if row["total"] >= 2]
    best_records = sorted(qualified, key=lambda row: (row["weighted_win_pct"], row["total"], row["wins"]), reverse=True)[:8]
    worst_records = sorted(qualified, key=lambda row: (row["weighted_win_pct"], -row["total"], -row["wins"]))[:8]
    most_active = sorted(fighter_records, key=lambda row: (row["total"], row["wins"]), reverse=True)[:8]

    summary_serialized = {key: serialize_value(value) for key, value in summary.items()}
    summary_serialized["ppv_slug"] = slug
    summary_serialized["logo_filename"] = stage_to_filename(ppv_name or "")

    return {
        "event": summary_serialized,
        "biggest_upsets": [{key: serialize_value(value) for key, value in row.items()} for row in upsets_raw],
        "best_records": best_records,
        "worst_records": worst_records,
        "most_active": most_active,
        "editions": [{key: serialize_value(value) for key, value in row.items()} for row in editions_raw],
        "fights": [
            {
                **{key: serialize_value(value) for key, value in fight.items() if key != "fighters"},
                "fighters": [{key: serialize_value(value) for key, value in fighter.items()} for fighter in fight["fighters"]],
            }
            for fight in fights_raw
        ],
    }

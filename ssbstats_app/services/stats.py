import logging
import time
from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories.base import query_failure_count, select_view_dicts, select_view_row
from ssbstats_app.repositories import comparisons, elo, events, fight_detail, fighters, fights, leaderboards, lookups, power, seasons
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.services.fight_story import get_upset_ranks
from ssbstats_app.services.ppv import get_event_hub, get_events_data
from ssbstats_app.services.records import get_record_book
from ssbstats_app.services.search import get_search_index
from ssbstats_app.services.stages import get_stage_hub, get_stages_data
from ssbstats_app.utils import event_to_slug, fighter_to_filename, normalize_champ_name, serialize_value, stage_to_filename


def build_index_payload():
    """Build the roster payload for the landing page (grid cards and the roster globe)."""
    fighters = get_fighters()
    current_champs = lookups.get_current_champions()
    # Both come from in-memory caches kept warm by keep_fighter_caches_warm().
    try:
        brands = lookups.get_fighter_brands()
    except Exception:
        brands = {}
    try:
        power_scores = power.get_career_power_scores()
    except Exception:
        power_scores = {}
    payload = []
    for fighter in fighters:
        key = fighter.lower()
        score = power_scores.get(key, {})
        payload.append({
            "name": fighter,
            "filename": fighter_to_filename(fighter),
            "titles": [normalize_champ_name(title) for title in current_champs.get(key, [])],
            "brand": brands.get(key, ""),
            "power_score": score.get("power_score"),
            "power_rank": score.get("power_rank"),
        })
    return payload


# Major titles first, then the rest; anything unlisted sorts last alphabetically.
_CHAMPIONSHIP_ORDER = ["Melee", "Brawl", "Ultimate", "Smash Bros.", "Unified Tag"]


@ttl_cache(6 * 60 * 60)
def get_home_summary():
    """League totals for the homepage. Cached; rebuilt by the warmer when data changes."""
    rows = select_view_dicts(
        """
        SELECT (SELECT COUNT(*) FROM Fight) AS fights,
               (SELECT MAX(Season_ID) FROM Season) AS seasons,
               (SELECT COUNT(*) FROM ChampionshipHistory) AS title_reigns,
               (SELECT COUNT(*) FROM PPV) AS ppvs
        """
    )
    row = rows[0] if rows else {}
    return {key: int(row.get(key) or 0) for key in ("fights", "seasons", "title_reigns", "ppvs")}


def home_champions(fighters):
    """Current champions from the roster payload, major titles first."""
    champions = [
        {"title": title, "name": f["name"], "filename": f["filename"], "brand": f.get("brand", "")}
        for f in fighters for title in f["titles"]
    ]

    def order(champ):
        title = champ["title"]
        return (_CHAMPIONSHIP_ORDER.index(title) if title in _CHAMPIONSHIP_ORDER else len(_CHAMPIONSHIP_ORDER), title)

    return sorted(champions, key=order)


def home_belts(fighters):
    """Every championship with its current holder(s), for the globe's 12 pentagon tiles."""
    from ssbstats_app.services.content import get_autocomplete_data

    canonical = {f["name"].lower(): f["name"] for f in fighters}
    holders = {}
    for fighter_key, titles in lookups.get_current_champions().items():
        for title in titles:
            holders.setdefault(title, []).append(canonical.get(fighter_key, fighter_key))
    return [
        {"title": title, "display": normalize_champ_name(title), "champions": holders.get(title, [])}
        for title in get_autocomplete_data("championships")
    ]


def home_top_fighters(fighters, count=5):
    """Top of the all-time power rankings from the roster payload."""
    ranked = [f for f in fighters if f.get("power_rank")]
    return sorted(ranked, key=lambda f: f["power_rank"])[:count]


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


# Entries are rebuilt by keep_fighter_caches_warm() when the data changes; the TTL is
# only a fallback (e.g. if the background thread isn't running).
_FIGHTER_CACHE_SECONDS = 6 * 60 * 60


@ttl_cache(_FIGHTER_CACHE_SECONDS)
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


@ttl_cache(_FIGHTER_CACHE_SECONDS)
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


@ttl_cache(_FIGHTER_CACHE_SECONDS)
def get_leaderboard_payload(season):
    """Return leaderboard rows with awards and title badges merged in. Cached per season
    ("" is all-time); rebuilt by the warmer when data changes."""
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


@ttl_cache(_FIGHTER_CACHE_SECONDS)
def get_season_payload(season_id):
    """Assemble the payload for a single season detail page. Cached; rebuilt by the warmer."""
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
    for row in data.get("champ_history", []) + data.get("cashins", []):
        if row.get("Championship_Name"):
            row["Championship_Name"] = normalize_champ_name(row["Championship_Name"])
    for row in data.get("awards", []) + data.get("holistic", []):
        if row.get("Fighter_Name"):
            row["Fighter_Name"] = canonical_map.get(row["Fighter_Name"].lower(), row["Fighter_Name"])
    for row in data.get("cashins", []):
        for key in ("Fight_Winner_Name", "Fight_Loser_Name"):
            if row.get(key):
                row[key] = canonical_map.get(row[key].lower(), row[key])
    for row in data.get("calendar", []):
        row["slug"] = event_to_slug(row.get("PPV_Name"))
    for row in data.get("facts", []):
        row["in_progress"] = season_id == latest and (row.get("last_month") or 0) < 12
    _add_award_notes(season_id, data, canonical_map)
    data.pop("prev_records", None)
    data.pop("team_records", None)

    return {
        key: [{field: serialize_value(value) for field, value in row.items()} for row in rows]
        for key, rows in data.items()
    }


def _add_award_notes(season, data, canonical_map):
    """The numbers behind each award, shown under the winner. Breakout and Most Disappointing compare
    with the previous season, so fighters with no previous season (Season 1, Ultimate newcomers) get none.

    Each note is {"type": "change", "before": {...}, "after": {...}, "delta": n} or
    {"type": "stats", "items": [{"label", "value"}], "titles": [names]}.
    """
    key = lambda name: (name or "").lower().strip()
    scores = power.get_all_season_power_scores()
    now_ps, prev_ps = scores.get(season, {}), scores.get(season - 1, {})
    now_rec = {key(r.get("Fighter_Name")): r for r in data.get("rankings", [])}
    prev_rec = {key(r.get("Fighter_Name")): r for r in data.get("prev_records", [])}
    titles = {key(r.get("Fighter_Name")): r.get("Titles_Held") for r in data.get("holistic", [])}

    def record(row):
        return f"{int(row.get('Wins') or 0)}–{int(row.get('Losses') or 0)}" if row else None

    def change(name):
        k = key(name)
        if k not in prev_ps or k not in now_ps:
            return None
        before, after = prev_ps[k]["power_score"], now_ps[k]["power_score"]
        return {
            "type": "change",
            "before": {"season": season - 1, "score": before, "record": record(prev_rec.get(k))},
            "after": {"season": season, "score": after, "record": record(now_rec.get(k))},
            "delta": round(after - before, 1),
        }

    def superstar(name):
        k = key(name)
        items = []
        if k in now_ps:
            items.append({"label": "Power rank", "value": f"#{now_ps[k]['power_rank']}", "score": now_ps[k]["power_score"]})
        if record(now_rec.get(k)):
            items.append({"label": "Record", "value": record(now_rec[k])})
        held = [t.strip() for t in str(titles.get(k) or "").split(",") if t.strip()]
        return {"type": "stats", "items": items, "titles": held} if items or held else None

    def tag_months(names):
        # Months this season the pair held the tag titles (same rule as the title timeline).
        wanted = {key(n) for n in names}
        reigns = {}
        for r in data.get("champ_history", []):
            if str(r.get("Championship_Name", "")).startswith("Unified Tag"):
                reigns.setdefault((r["Season_Won"], r["Month_Won"], r["Season_Lost"], r["Month_Lost"]), []).append(r)
        last = next((f.get("last_month") for f in data.get("facts", []) if f.get("in_progress")), 12)
        months = 0
        for (sw, mw, sl, ml), rows in reigns.items():
            if {key(r["Fighter_Name"]) for r in rows} != wanted:
                continue
            start = 1 if sw < season else mw + (0 if any(r.get("inaugural") for r in rows) else 1)
            end = last if sl is None else (12 if sl > season else ml)
            months += max(0, end - start + 1)
        return months

    def tag_team(names):
        a, b = sorted(key(n) for n in names)[:2]
        row = next((r for r in data.get("team_records", []) if sorted([key(r["f1"]), key(r["f2"])]) == [a, b]), None)
        items = []
        if row and (row["wins"] or row["losses"]):
            items.append({"label": "Team record", "value": f"{int(row['wins'])}–{int(row['losses'])}"})
        months = tag_months(names)
        if months:
            items.append({"label": "With the tag titles", "value": f"{months} mo"})
        return {"type": "stats", "items": items, "titles": []} if items else None

    by_award = {}
    for row in data.get("awards", []):
        by_award.setdefault(row.get("Award_Name") or "", []).append(row)
    for award, rows in by_award.items():
        names = [r.get("Fighter_Name") for r in rows]
        lower = award.lower()
        if "superstar" in lower:
            note = superstar(names[0])
        elif "improved" in lower or "disappoint" in lower:
            note = change(names[0])
        elif "tag" in lower and len(names) >= 2:
            note = tag_team(names)
        else:
            note = None
        for r in rows:
            r["note"] = note


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
        # No-contests neither extend nor break a streak (same as the allwinstreaks view).
        rows = [row for row in rows if str(row.get("Decision") or "").upper() in ("W", "L")]
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
        if championship:
            # One row for both sides: the champion's record defending titles, the challenger's
            # record challenging for them (title fights where they weren't the champion).
            defending = lambda row: str(row.get("DefendingIndicator") or "").upper() not in ("", "N", "0", "NONE")
            if participant["defending"]:
                role, role_record = "defending", record_from_rows(rows, defending)
            else:
                role, role_record = "challenging", record_from_rows(rows, lambda row: bool(row.get("Championship_Name")) and not defending(row))
            contextual_records.append(
                {
                    "label": "Defending / challenging",
                    "record": role_record,
                    "role": role,
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
            # Count any shared fight where one beat the other, whatever the match size,
            # matching the head-to-head page. Other participants' rows are ignored.
            # Names aren't always cased the same in the data (e.g. "DK" vs "Dk"), so match
            # case-insensitively and normalize to this fight's spelling.
            pair_names = {f1.lower(): f1, f2.lower(): f2}
            pair_rows = [
                {**row, "Fighter_Name": pair_names[str(row.get("Fighter_Name") or "").lower()]}
                for row in rows
                if str(row.get("Fighter_Name") or "").lower() in pair_names
            ]
            decisions = {str(row.get("Decision") or "").upper() for row in pair_rows}
            if len(pair_rows) == 2 and decisions == {"W", "L"}:
                direct_prior.append(pair_rows)

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


def _record_summary(rows):
    """First row of a W/L view in the compare page's summary shape."""
    if not rows:
        return {"wins": 0, "losses": 0, "win_pct": "0.00%"}
    row = rows[0]
    return {"wins": serialize_value(row.get("Wins", 0)), "losses": serialize_value(row.get("Losses", 0)), "win_pct": str(row.get("Win Percentage", "0.00%"))}


@ttl_cache(_FIGHTER_CACHE_SECONDS)
def get_compare_side(name):
    """One fighter's half of the comparison payload. Opponent-independent, so it's cached per
    fighter and rebuilt by the warmer; a comparison then only queries what's specific to the pair."""
    raw = comparisons.get_fighter_comparison_rows(name)
    ps_all = power.get_all_season_power_scores()
    ps_career = power.get_career_power_scores()

    holistic = []
    for row in raw.get("holistic", []):
        serialized = {key: serialize_value(value) for key, value in row.items()}
        if serialized.get("Titles_Held"):
            serialized["Titles_Held"] = normalize_champ_name(serialized["Titles_Held"])
        holistic.append(serialized)

    champs = raw.get("champs", [])
    nk = name.lower()
    return {
        "name": name,
        "image": fighter_to_filename(name) + ".png",
        "career": _record_summary(raw.get("career", [])),
        "by_season": [
            {"season": str(row.get("Season", "")), "wins": serialize_value(row.get("Wins", 0)), "losses": serialize_value(row.get("Losses", 0)), "win_pct": str(row.get("Win Percentage", "0.00%"))}
            for row in raw.get("season", [])
        ],
        "holistic": holistic,
        "running": [
            {"season": row.get("Season"), "month": row.get("Month"), "week": row.get("Week"), "decision": row.get("Decision"), "career_win_pct": str(row.get("Career_Running_Win_Pct", "0.00%"))}
            for row in raw.get("running", [])
        ],
        "unique_champs": int(champs[0].get("total", 0)) if champs else 0,
        "champ_stats": _record_summary(raw.get("champ_stats", [])),
        "awards": [{"season": int(row.get("Season_ID", 0)), "name": str(row.get("Award_Name", ""))} for row in raw.get("awards", [])],
        "elo_history": [
            {"fight_id": int(row.get("fight_id", 0)), "season": int(row.get("season", 0)), "month": int(row.get("month", 0)), "week": row.get("week"), "elo_before": float(row.get("elo_before", 0)), "elo_after": float(row.get("elo_after", 0))}
            for row in raw.get("elo_history", [])
        ],
        "career_power_score": ps_career.get(nk, {}),
        "power_scores_by_season": {str(season): ps_all[season][nk] for season in sorted(ps_all.keys()) if nk in ps_all[season]},
        "brand": lookups.get_fighter_brands().get(nk, ""),
    }


@ttl_cache(_FIGHTER_CACHE_SECONDS)
def get_compare_roster_maxes():
    """Roster-wide maximums for scaling the comparison radar (career and single-season)."""
    raw = comparisons.get_roster_max_rows()
    months = (raw.get("roster_max_months") or [{}])[0]
    wr_row = (raw.get("roster_max_wr") or [{}])[0]
    ev_row = (raw.get("roster_max_ev") or [{}])[0]
    tc_row = (raw.get("roster_max_champs") or [{}])[0]
    season_row = (raw.get("season_roster_max_holistic") or [{}])[0]
    return {
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


def _shared_fights(f1, f2):
    """Every fight both fighters were in, newest first, shaped like the fight log rows."""
    rows = fights.get_fight_log({"fighter": f1, "fighter2": f2, "fighter_op2": "and"}, page=1, per_page=500)
    return [
        {**{key: serialize_value(value) for key, value in fight.items() if key != "fighters"},
         "fighters": [{key: serialize_value(value) for key, value in fighter.items()} for fighter in fight["fighters"]]}
        for fight in rows
    ]


@ttl_cache(_FIGHTER_CACHE_SECONDS)
def get_compare_payload(f1, f2):
    """Assemble the full fighter-vs-fighter comparison payload.

    Both fighters' halves and the roster maximums come from caches, so only the pair's
    head-to-head record and shared fights are queried. The warmer clears this cache when
    data changes.
    """
    with ThreadPoolExecutor(max_workers=5) as pool:
        side1 = pool.submit(get_compare_side, f1)
        side2 = pool.submit(get_compare_side, f2)
        maxes = pool.submit(get_compare_roster_maxes)
        h2h = pool.submit(comparisons.get_head_to_head_record, f1, f2)
        shared = pool.submit(_shared_fights, f1, f2)
        side1, side2, maxes, h2h, shared = side1.result(), side2.result(), maxes.result(), h2h.result(), shared.result()

    def with_record(side, index):
        row = h2h[index] if len(h2h) > 1 else {}
        return {**side, "h2h_wins": int(row.get("Wins", 0) or 0), "h2h_losses": int(row.get("Losses", 0) or 0)}

    return {
        "fighter1": with_record(side1, 0),
        "fighter2": with_record(side2, 1),
        "shared_fights": shared,
        **maxes,
    }


def _build_fight_result_summary(participants, winners, losers, fight_type, championship=""):
    """Build a concise fight result string for the detail page."""
    fight_type_lower = (fight_type or "").lower()
    winner_names = " & ".join(participant["name"] for participant in winners) if winners else ""
    loser_names = " & ".join(participant["name"] for participant in losers) if losers else ""

    if participants and all(participant["decision"] == "NC" for participant in participants):
        return "No contest"

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

    if not winners and participants:
        return " vs. ".join(participant["name"] for participant in participants)

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


_DATA_CHECK_SECONDS = 60
_DATA_TABLES = "Fight, Results, Elo, AwardHistory, Fighter, Championship"


def _data_fingerprint():
    """Return a cheap fingerprint that changes whenever fight data is added or edited."""
    return tuple(row[1] for row in select_view_row(f"CHECKSUM TABLE {_DATA_TABLES}"))


def keep_fighter_caches_warm():
    """Pre-build every fighter's payloads, then rebuild only when the data changes.

    A checksum query every minute is nearly free; the full rebuild (~70 fighters)
    only runs at startup and after new fights, Elo or awards are entered. This keeps
    profiles instant without putting steady load on the small RDS instance.
    """
    log = logging.getLogger(__name__)
    built_for = None
    while True:
        try:
            fingerprint = _data_fingerprint()
        except Exception:
            log.exception("Could not check for data changes")
            time.sleep(_DATA_CHECK_SECONDS)
            continue
        if fingerprint != built_for:
            started = time.time()
            failures_before = query_failure_count()
            try:
                power.get_all_season_power_scores.refresh()
                power.get_career_power_scores.refresh()
                lookups.get_fighter_brands.refresh()
                get_home_summary.refresh()
                get_record_book.refresh()
                get_championships_data.refresh()
                get_events_data.refresh()
                get_event_hub.cache_clear()   # event pages rebuild on demand from the fresh data
                get_stages_data.refresh()
                get_stage_hub.cache_clear()   # stage pages too
                get_upset_ranks.refresh()
                get_compare_roster_maxes.refresh()
                get_compare_payload.cache_clear()  # pairs rebuild on demand from the per-fighter halves
                latest = lookups.get_latest_season()
                get_search_index.refresh()
                get_leaderboard_payload.refresh("")
                for season in range(1, latest + 1):
                    get_leaderboard_payload.refresh(str(season))
                    get_season_payload.refresh(season)
                    time.sleep(0.2)
                names = lookups.get_all_fighters()
                for name in names:
                    get_fighter_profile_payload.refresh(name)
                    get_fighter_advanced_payload.refresh(name)
                    get_compare_side.refresh(name)
                    time.sleep(0.2)  # spread the rebuild out so it never spikes the database
                # Only mark this data version done if every query succeeded; otherwise retry next check.
                if query_failure_count() == failures_before:
                    built_for = fingerprint
                log.info("Rebuilt fighter caches for %d fighters in %.0fs", len(names), time.time() - started)
            except Exception:
                log.exception("Fighter cache rebuild failed; will retry")
        time.sleep(_DATA_CHECK_SECONDS)

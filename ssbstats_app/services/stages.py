"""Shape stage history for the Stages page and each stage's history page."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories import fights, stages
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.services.ppv import _weighted_win_pct
from ssbstats_app.utils import fighter_to_filename, normalize_champ_name, serialize_value, stage_to_filename

STAGE_ART = Path(__file__).resolve().parents[2] / "static" / "assets" / "stages"
# The Smash game each stage debuted in, oldest first (Location_Origin).
ORIGIN_ORDER = ["64", "Melee", "Brawl", "3DS", "Wii U", "Ultimate"]
MIN_FIGHTS_FOR_RECORDS = 5


def _canonical():
    from ssbstats_app.services.content import get_autocomplete_data

    known = {n.lower(): n for n in get_autocomplete_data("fighters")}
    return lambda n: known.get((n or "").lower(), n)


def _person(name, canonical):
    name = canonical(name)
    return {"name": name, "filename": fighter_to_filename(name)}


def _titles_won_by_stage():
    """Every title reign keyed by the stage it was won on."""
    won = {}
    for t in get_championships_data()["titles"]:
        for reign in t["reigns"]:
            where = reign["won"]
            if not where.get("location"):
                continue
            won.setdefault(where["location"], []).append({
                "title": t["name"], "slug": t["slug"], "belt": t["belt"], "trophy": t["trophy"],
                "champions": reign["champions"], "label": reign["label"],
                "season": where["season"], "month": where["month"], "ppv": where.get("ppv"),
                "fight_id": where.get("fight_id"), "fight_type": where.get("fight_type"),
            })
    return won


@ttl_cache(6 * 60 * 60)
def get_stages_data():
    """Every stage with its totals and top winner. The warmer refreshes this when data changes."""
    canonical = _canonical()
    kings = {r["Location_Name"]: r for r in stages.get_stage_kings()}
    won_here = _titles_won_by_stage()
    rows = []
    for r in stages.get_stage_index():
        name = r["Location_Name"]
        slug = stage_to_filename(name)
        king = kings.get(name)
        rows.append({
            "name": name,
            "slug": slug,
            "image": slug if (STAGE_ART / f"{slug}.png").exists() else None,
            "series": r["Location_GameSeries"],
            "origin": r["Location_Origin"],
            "fights": int(r["fights"]),
            "title_fights": int(r["title_fights"]),
            "title_changes": sum(1 for t in won_here.get(name, []) if not t["trophy"]),
            "ppv_fights": int(r["ppv_fights"]),
            "fighters": int(r["fighters"]),
            "first": r["first_season"],
            "last": r["last_season"],
            "king": {**_person(king["Fighter_Name"], canonical), "wins": int(king["Wins"]), "losses": int(king["Losses"])} if king else None,
        })
    used = [s for s in rows if s["fights"]]
    origins = sorted({s["origin"] for s in used if s["origin"]},
                     key=lambda o: ORIGIN_ORDER.index(o) if o in ORIGIN_ORDER else len(ORIGIN_ORDER))
    return {"stages": used, "unused": [s for s in rows if not s["fights"]], "origins": origins}


def get_stage(slug):
    """One stage's index row, or None."""
    data = get_stages_data()
    return next((s for s in data["stages"] + data["unused"] if s["slug"] == slug), None)


@ttl_cache(6 * 60 * 60)
def get_stage_hub(slug):
    """One stage's all-time history. The warmer clears this cache when data changes."""
    stage = get_stage(slug)
    if stage is None:
        return None
    name = stage["name"]
    canonical = _canonical()

    with ThreadPoolExecutor(max_workers=4) as pool:
        records_f = pool.submit(stages.get_stage_fighter_records, name)
        upsets_f = pool.submit(stages.get_stage_biggest_upsets, name, 5)
        rivals_f = pool.submit(stages.get_stage_rivalries, name, 5)
        fights_f = pool.submit(fights.get_fight_log, {"location": name}, 1, 3000)
        records_raw, upsets_raw, rivals_raw, fight_rows = records_f.result(), upsets_f.result(), rivals_f.result(), fights_f.result()

    records = []
    for row in records_raw:
        wins, losses = int(row["wins"] or 0), int(row["losses"] or 0)
        if not wins + losses:
            continue
        records.append({**_person(row["Fighter_Name"], canonical), "wins": wins, "losses": losses, "total": wins + losses,
                        "win_pct": wins / (wins + losses) * 100, "weighted": _weighted_win_pct(wins, losses)})
    qualified = [r for r in records if r["total"] >= MIN_FIGHTS_FOR_RECORDS]

    upsets = [{
        "fight_id": row["Fight_ID"], "season": row["Season"], "month": row["Month"],
        "winner": _person(row["winner_name"], canonical), "loser": _person(row["loser_name"], canonical),
        "gap": round(float(row["upset_gap"] or 0)), "title": normalize_champ_name(row.get("Championship_Name")),
    } for row in upsets_raw]

    rivalries = []
    for row in rivals_raw:
        total, a_wins = int(row["fights"]), int(row["a_wins"])
        rivalries.append({"a": _person(row["fighter_a"], canonical), "b": _person(row["fighter_b"], canonical),
                          "fights": total, "a_wins": a_wins, "b_wins": total - a_wins, "last_fight_id": row["last_fight_id"]})

    titles = sorted(_titles_won_by_stage().get(name, []), key=lambda t: (-(t["season"] or 0), -(t["month"] or 0)))
    ppv_nights = {(f["ppv"], f["season"], f["month"]) for f in fight_rows if f.get("ppv")}

    return {
        "stage": stage,
        "ppv_nights": len(ppv_nights),
        "most_wins": sorted(records, key=lambda r: (-r["wins"], r["losses"]))[:5],
        "best": sorted(qualified, key=lambda r: (-r["weighted"], -r["total"]))[:5],
        "worst": sorted(qualified, key=lambda r: (r["weighted"], -r["total"]))[:5],
        "upsets": upsets,
        "rivalries": rivalries,
        "titles": titles,
        "fights": [{**{k: serialize_value(v) for k, v in f.items() if k != "fighters"},
                    "fighters": [{k: serialize_value(v) for k, v in x.items()} for x in f["fighters"]]} for f in fight_rows],
    }

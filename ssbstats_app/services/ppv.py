"""Shape PPV history for the Events page (calendar + season by season) and each event's history page."""

from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories import events, fights
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.utils import event_to_slug, fighter_to_filename, normalize_champ_name, serialize_value, stage_to_filename

# Marquee events and the holistic_view column that records each season's winner(s).
EVENT_WINNERS = {
    "Royal Rumble": ("Won_Royal_Rumble", None),
    "Money in the Bank": ("Won_Money_In_The_Bank", None),
    "Final Destination Tournament": ("Won_Tournament", "{} bracket"),
    "Championship Scramble": ("Won_Scramble", "{} scramble"),
    "Smash Series": ("Won_Smash_Series", None),
}


def _person(name, canonical):
    name = canonical(name)
    return {"name": name, "filename": fighter_to_filename(name)}


def _weighted_win_pct(wins, losses, prior=0.5, strength=4):
    """Win percentage pulled toward 50% for small samples, so 2-0 doesn't outrank 12-3."""
    return (wins + prior * strength) / (wins + losses + strength) * 100


@ttl_cache(6 * 60 * 60)
def get_events_data():
    """Every PPV and every edition, with the champions crowned and event winners at each.
    Rebuilt by the warmer when data changes."""
    from ssbstats_app.services.content import get_autocomplete_data

    known = {n.lower(): n for n in get_autocomplete_data("fighters")}
    canonical = lambda n: known.get((n or "").lower(), n)

    with ThreadPoolExecutor(max_workers=3) as pool:
        editions_future = pool.submit(events.get_all_ppvs)
        winners_future = pool.submit(events.get_event_winners)
        about_future = pool.submit(events.get_ppv_descriptions)
        edition_rows, winner_rows, about = editions_future.result(), winners_future.result(), about_future.result()
    titles = get_championships_data()["titles"]

    # Champions crowned at each edition: reigns won in a fight on that PPV card. The yearly
    # Smash Bros. trophy isn't a title change; it's listed with the event's winners instead.
    crowned, trophies = {}, {}
    for title in titles:
        for reign in title["reigns"]:
            won = reign["won"]
            if not (won.get("ppv") and won.get("fight_id")):
                continue
            if title["trophy"]:
                trophies.setdefault((won["ppv"], won["season"]), []).extend(
                    {**c, "detail": f"{title['name']} trophy"} for c in reign["champions"])
                continue
            crowned.setdefault((won["ppv"], won["season"], won["month"]), []).append({
                "title": title["name"], "belt": title["belt"], "slug": title["slug"],
                "champions": reign["champions"], "label": reign["label"], "fight_id": won["fight_id"],
                "cash_in": won.get("fight_type") == "Cash In",
            })

    winners = {}
    for row in winner_rows:
        for ppv_name, (col, detail) in EVENT_WINNERS.items():
            value = row.get(col)
            if value:
                winners.setdefault((ppv_name, row["Season"]), []).append({
                    **_person(row["Fighter_Name"], canonical),
                    "detail": detail.format(value) if detail else None,
                })

    ppvs, editions = {}, []
    for row in edition_rows:
        name = row["PPV_Name"]
        edition = {
            "ppv": name, "slug": event_to_slug(name), "logo": stage_to_filename(name),
            "season": int(row["Season"]), "month": int(row["Month"]),
            "fights": int(row["fight_count"]), "title_fights": int(row["title_fights"] or 0),
            "location": row.get("Location_Name"), "stage": stage_to_filename(row.get("Location_Name") or ""),
            "crowned": crowned.get((name, row["Season"], row["Month"]), []),
            "winners": winners.get((name, row["Season"]), []) + trophies.get((name, row["Season"]), []),
        }
        editions.append(edition)
        p = ppvs.setdefault(name, {"name": name, "slug": edition["slug"], "logo": edition["logo"], "months": set(),
                                   "about": (about.get(name) or "").strip(),
                                   "editions": 0, "fights": 0, "title_fights": 0, "title_changes": 0,
                                   "first": edition["season"], "last": edition["season"]})
        p["months"].add(edition["month"])
        p["editions"] += 1
        p["fights"] += edition["fights"]
        p["title_fights"] += edition["title_fights"]
        p["title_changes"] += len(edition["crowned"])
        p["first"], p["last"] = min(p["first"], edition["season"]), max(p["last"], edition["season"])

    for p in ppvs.values():
        p["month"] = min(p["months"])
        p["months"] = sorted(p["months"])

    # The yearly calendar: each month's current PPV, plus any it replaced in that slot.
    calendar = []
    for month in range(1, 13):
        in_slot = sorted((p for p in ppvs.values() if month in p["months"]), key=lambda p: -p["last"])
        if in_slot:
            calendar.append({"month": month, "ppv": in_slot[0], "previously": in_slot[1:]})

    editions.sort(key=lambda e: (-e["season"], -e["month"]))
    seasons = sorted({e["season"] for e in editions})
    return {
        "calendar": calendar,
        "seasons": seasons,
        "editions_by_season": {s: sorted((e for e in editions if e["season"] == s), key=lambda e: e["month"]) for s in seasons},
        "ppvs": ppvs,
        "totals": {"ppvs": len(ppvs), "editions": len(editions), "fights": sum(e["fights"] for e in editions)},
    }


@ttl_cache(6 * 60 * 60)
def get_event_hub(slug):
    """One PPV's all-time history. The warmer clears this cache when data changes."""
    from ssbstats_app.services.content import get_autocomplete_data

    data = get_events_data()
    ppv = next((p for p in data["ppvs"].values() if p["slug"] == slug), None)
    if ppv is None:
        return None
    name = ppv["name"]
    known = {n.lower(): n for n in get_autocomplete_data("fighters")}
    canonical = lambda n: known.get((n or "").lower(), n)

    with ThreadPoolExecutor(max_workers=4) as pool:
        summary_f = pool.submit(events.get_event_summary, name)
        records_f = pool.submit(events.get_event_fighter_records, name)
        upsets_f = pool.submit(events.get_event_biggest_upsets, name, 5)
        fights_f = pool.submit(fights.get_fight_log, {"ppv": name}, 1, 2000)
        summary, records_raw, upsets_raw, fight_rows = summary_f.result(), records_f.result(), upsets_f.result(), fights_f.result()

    records = []
    for row in records_raw:
        wins, losses = int(row.get("wins") or 0), int(row.get("losses") or 0)
        records.append({**_person(row["Fighter_Name"], canonical), "wins": wins, "losses": losses, "total": wins + losses,
                        "win_pct": wins / (wins + losses) * 100 if wins + losses else 0,
                        "weighted": _weighted_win_pct(wins, losses)})
    qualified = [r for r in records if r["total"] >= 3]

    upsets = [{
        "fight_id": row["Fight_ID"], "season": row["Season"], "month": row["Month"],
        "winner": _person(row["winner_name"], canonical), "loser": _person(row["loser_name"], canonical),
        "gap": round(float(row["upset_gap"] or 0)), "title": normalize_champ_name(row.get("Championship_Name")),
    } for row in upsets_raw]

    editions = sorted((e for e in sum(data["editions_by_season"].values(), []) if e["slug"] == slug), key=lambda e: -e["season"])
    return {
        "ppv": ppv,
        "unique_fighters": int((summary or {}).get("unique_fighters") or 0),
        "editions": editions,
        "latest": editions[0] if editions else None,
        "best": sorted(qualified, key=lambda r: (-r["weighted"], -r["total"]))[:5],
        "worst": sorted(qualified, key=lambda r: (r["weighted"], -r["total"]))[:5],
        "most_active": sorted(records, key=lambda r: (-r["total"], -r["wins"]))[:5],
        "upsets": upsets,
        "fights": [{**{k: serialize_value(v) for k, v in f.items() if k != "fighters"},
                    "fighters": [{k: serialize_value(v) for k, v in x.items()} for x in f["fighters"]]} for f in fight_rows],
    }

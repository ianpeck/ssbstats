"""Shape championship lineages for the Championships page and the per-title history pages."""

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories import championships as repo
from ssbstats_app.repositories import events, fights
from ssbstats_app.utils import fighter_to_filename, normalize_champ_name, serialize_value

TIER_ORDER = ["Major", "Tag", "Minor", "Specialty"]
TIER_LABELS = {"Major": "Major titles", "Tag": "Tag team", "Minor": "Minor titles", "Specialty": "Yearly trophy"}
# Display order within each tier (minors fill rows of three: Animal, Human, Monster / Special, Hardcore, Chaos).
TITLE_ORDER = ["Melee", "Brawl", "Ultimate", "Animal", "Human", "Monster", "Special", "Hardcore", "Chaos"]
TROPHY = "Smash Bros."   # won once a year, not held and defended


def display_name(name):
    """"Unified Tag 1" and "Unified Tag 2" are the two halves of one title."""
    return "Unified Tag" if (name or "").startswith("Unified Tag") else normalize_champ_name(name)


def title_slug(name):
    return re.sub(r"[^a-z0-9]", "", display_name(name).lower())


def _abs_month(season, month):
    return (season - 1) * 12 + month


def _people(names, canonical):
    return [{"name": canonical(n), "filename": fighter_to_filename(canonical(n))} for n in names]


def _group_reigns(rows):
    """Tag partners share a reign (same dates); keep lineage order."""
    groups = []
    for row in rows:
        key = (row["Season_Won"], row["Month_Won"], row["Season_Lost"], row["Month_Lost"])
        if groups and groups[-1]["key"] == key:
            groups[-1]["names"].append(row["Fighter_Name"])
            groups[-1]["inaugural"] = groups[-1]["inaugural"] or bool(row["inaugural"])
            continue
        groups.append({"key": key, "names": [row["Fighter_Name"]], "inaugural": bool(row["inaugural"]), "row": row})
    return groups


def _defenses(fight_rows, names, start, end):
    """Title fights a reign's champion(s) won as the defending champion, between won and lost."""
    lowered = {n.lower() for n in names}
    count = 0
    for fight in fight_rows:
        when = _abs_month(fight["season"], fight["month"])
        if not start <= when <= end:
            continue
        if any((f["name"] or "").lower() in lowered and str(f.get("defending") or "").lower() == "y"
               and str(f.get("win") or "").lower() == "w" for f in fight["fighters"]):
            count += 1
    return count


def _bracket_defenses(rounds, names, start, end):
    """Bracket rounds a reign's champion(s) won between winning and losing the title."""
    lowered = {n.lower() for n in names}
    return sum(1 for r in rounds
               if (r["Fighter_Name"] or "").lower() in lowered and start <= _abs_month(r["Season"], r["Month"]) <= end)


def _build_title(info, rows, fight_rows, now, canonical, bracket_rounds):
    name = display_name(info["Championship_Name"])
    trophy = info["Championship_Name"] == TROPHY
    now_abs = _abs_month(*now)

    reigns = []
    for index, group in enumerate(_group_reigns(rows)):
        row = group["row"]
        current = row["Season_Lost"] is None
        months = row["months_held"]
        if months is None:
            months = now_abs - _abs_month(row["Season_Won"], row["Month_Won"])
        start = _abs_month(row["Season_Won"], row["Month_Won"])
        end = now_abs if current else _abs_month(row["Season_Lost"], row["Month_Lost"])
        reigns.append({
            "number": index + 1,
            "champions": _people(group["names"], canonical),
            "label": " & ".join(canonical(n) for n in group["names"]),
            "won": {"season": row["Season_Won"], "month": row["Month_Won"], "week": serialize_value(row["won_week"]),
                    "fight_id": row["won_fight_id"], "ppv": row["won_ppv"], "location": row["won_location"],
                    "fight_type": row["won_fight_type"]},
            "lost": None if current else {"season": row["Season_Lost"], "month": row["Month_Lost"]},
            "current": current,
            "inaugural": group["inaugural"],
            "months": int(months or 0),
            "title_defenses": 0 if trophy else _defenses(fight_rows, group["names"], start, end),
            # Only the major titles are decided in brackets.
            "bracket_defenses": _bracket_defenses(bracket_rounds, group["names"], start, end) if info["tier"] == "Major" else 0,
        })

    for reign in reigns:
        reign["defenses"] = reign["title_defenses"] + reign["bracket_defenses"]

    # A reign ends in the fight where the next champion won the title.
    if not trophy:
        for reign, nxt in zip(reigns, reigns[1:]):
            lost = reign["lost"]
            if lost and (nxt["won"]["season"], nxt["won"]["month"]) == (lost["season"], lost["month"]):
                lost.update({"week": nxt["won"]["week"], "fight_id": nxt["won"]["fight_id"], "ppv": nxt["won"]["ppv"]})

    # Per-champion totals for this title (tag partners each get credit).
    reign_counts, defense_counts, month_counts = Counter(), Counter(), Counter()
    for reign in reigns:
        for person in reign["champions"]:
            reign_counts[person["name"]] += 1
            defense_counts[person["name"]] += reign["defenses"]
            month_counts[person["name"]] += reign["months"]

    def leaders(counter, limit=5):
        return [{"name": n, "filename": fighter_to_filename(n), "value": v} for n, v in counter.most_common(limit) if v > 0]

    current = [r for r in reigns if r["current"]]
    longest = sorted((r for r in reigns if not trophy), key=lambda r: (-r["months"], r["number"]))[:5]
    first = reigns[0] if reigns else None
    return {
        "name": name,
        "slug": title_slug(name),
        "tier": info["tier"],
        "trophy": trophy,
        "belt": "tagteam" if info["tier"] == "Tag" else title_slug(name),
        "reigns": reigns,
        "reign_count": len(reigns),
        "champion_count": len(reign_counts),
        "title_fights": len(fight_rows),
        "current": current[-1] if current else None,
        "longest": longest,
        "most_reigns": leaders(reign_counts),
        "most_defenses": [] if trophy else leaders(defense_counts),
        "most_months": [] if trophy else leaders(month_counts),
        "since": {"season": first["won"]["season"], "month": first["won"]["month"]} if first else None,
        "recent": reigns[-6:],
        "fights": fight_rows,
    }


def _serialize_fights(rows):
    return [{**{k: serialize_value(v) for k, v in fight.items() if k != "fighters"},
             "fighters": [{k: serialize_value(v) for k, v in f.items()} for f in fight["fighters"]]} for fight in rows]


@ttl_cache(6 * 60 * 60)
def get_championships_data():
    """Every title's lineage, records and title fights. Rebuilt by the warmer when data changes."""
    from ssbstats_app.services.content import get_autocomplete_data

    known = {n.lower(): n for n in get_autocomplete_data("fighters")}
    canonical = lambda n: known.get((n or "").lower(), n)

    titles_raw = repo.get_championships()
    with ThreadPoolExecutor(max_workers=6) as pool:
        reigns_future = pool.submit(repo.get_reigns)
        bracket_future = pool.submit(repo.get_bracket_defenses)
        now_future = pool.submit(events.get_current_fight_date)
        fight_futures = {t["Championship_Name"]: pool.submit(fights.get_fight_log, {"championship": t["Championship_Name"]}, 1, 1000)
                         for t in titles_raw}
        reign_rows = reigns_future.result()
        bracket_rounds = bracket_future.result()
        now = now_future.result()
        fights_by_raw = {name: _serialize_fights(f.result()) for name, f in fight_futures.items()}

    merged = {}
    for t in titles_raw:
        display = display_name(t["Championship_Name"])
        entry = merged.setdefault(display, {"info": t, "rows": [], "fights": []})
        entry["rows"] += [r for r in reign_rows if r["Championship_Name"] == t["Championship_Name"]]
        entry["fights"] += fights_by_raw.get(t["Championship_Name"], [])

    titles = [_build_title(e["info"], e["rows"], e["fights"], now, canonical, bracket_rounds) for e in merged.values()]

    def order(t):
        tier = TIER_ORDER.index(t["tier"]) if t["tier"] in TIER_ORDER else len(TIER_ORDER)
        within = TITLE_ORDER.index(t["name"]) if t["name"] in TITLE_ORDER else len(TITLE_ORDER)
        return tier, within, t["name"]

    titles.sort(key=order)
    return {"titles": titles, "now": {"season": now[0], "month": now[1]}}


def get_championships_overview():
    """Titles grouped by tier for the Championships page (without the full fight archives)."""
    data = get_championships_data()
    groups = []
    for tier in TIER_ORDER:
        members = [{k: v for k, v in t.items() if k != "fights"} for t in data["titles"] if t["tier"] == tier]
        if members:
            groups.append({"tier": tier, "label": TIER_LABELS[tier], "titles": members})
    totals = {
        "titles": len(data["titles"]),
        "reigns": sum(t["reign_count"] for t in data["titles"] if not t["trophy"]),
        "champions": len({c["name"] for t in data["titles"] if not t["trophy"] for r in t["reigns"] for c in r["champions"]}),
    }
    return {"groups": groups, "totals": totals, "now": data["now"]}


def get_championship_detail(slug):
    data = get_championships_data()
    title = next((t for t in data["titles"] if t["slug"] == slug), None)
    if title is None:
        return None
    return {"title": title, "now": data["now"], "others": [{"name": t["name"], "slug": t["slug"], "belt": t["belt"]} for t in data["titles"]]}

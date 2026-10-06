"""The site-wide search index: every fighter, stage, event, title, season and page, as one small list.

The browser downloads it once and searches it locally, so typing never waits on the server.
"""

from urllib.parse import quote

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories.seasons import get_all_seasons
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.services.ppv import get_events_data
from ssbstats_app.services.stages import get_stages_data

PAGES = [
    ("Roster", "/", "users", "Every fighter, on the globe or in a grid"),
    ("Head to Head", "/head2head", "swords", "Compare any two fighters"),
    ("Power Rankings", "/leaderboard", "trophy", "All-time and season rankings"),
    ("Seasons", "/seasons", "calendar", "Season recaps and standings"),
    ("Championships", "/championships", "crown", "Every title and its lineage"),
    ("Record Book", "/records", "book-open", "All-time league records"),
    ("Events (PPVs)", "/events", "tv", "Every pay-per-view"),
    ("Stages", "/stages", "map", "Every stage and who rules it"),
    ("Fight Log", "/fights", "notebook", "Search every fight"),
    ("Ask AI", "/chat", "sparkles", "Ask the stats AI anything"),
    ("About", "/about", "info", "How the site works"),
]


def _img(folder, name):
    stem = name.rsplit(".", 1)[0]
    return f"/static/assets/{folder}/sm/{stem}.webp"


@ttl_cache(6 * 60 * 60)
def get_search_index():
    """Every searchable thing as {type, name, sub, url, img|icon}. The warmer refreshes this when data changes."""
    from ssbstats_app.services.stats import build_index_payload

    items = []
    for f in build_index_payload():
        sub = [f"#{f['power_rank']} all-time" if f.get("power_rank") else "Fighter"]
        sub += [f"{t} champion" for t in f["titles"]]
        items.append({"type": "Fighter", "name": f["name"], "sub": " · ".join(sub),
                      "url": f"/fighter/{quote(f['name'])}", "img": _img("fighters", f["filename"]), "rank": f.get("power_rank") or 999})

    for t in get_championships_data()["titles"]:
        current = (t.get("current") or {}).get("label")
        kind = "Trophy" if t["trophy"] else "Title"
        sub = f"{kind} · {'held by ' if not t['trophy'] else 'last won by '}{current}" if current else kind
        items.append({"type": "Title", "name": t["name"] if t["trophy"] else f"{t['name']} Championship", "sub": sub,
                      "url": f"/championships/{t['slug']}", "img": _img("belts", t["belt"])})

    for p in get_events_data()["ppvs"].values():
        items.append({"type": "Event", "name": p["name"], "sub": f"Pay-per-view · {p['editions']} events · {p['fights']} fights",
                      "url": f"/events/{p['slug']}", "img": _img("ppv", p["logo"])})

    for s in get_stages_data()["stages"]:
        sub = " · ".join(x for x in [s["series"], f"{s['fights']} fights"] if x)
        items.append({"type": "Stage", "name": s["name"], "sub": sub, "url": f"/stages/{s['slug']}",
                      "img": _img("stages", s["image"]) if s["image"] else None, "icon": "map-pin"})

    for season in get_all_seasons():
        era = "Brawl era" if season <= 5 else "Ultimate era"
        items.append({"type": "Season", "name": f"Season {season}", "sub": f"Recap, awards and standings · {era}",
                      "url": f"/seasons?season={season}", "icon": "calendar"})

    for name, url, icon, sub in PAGES:
        items.append({"type": "Page", "name": name, "sub": sub, "url": url, "icon": icon})
    return items

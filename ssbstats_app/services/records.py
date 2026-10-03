"""Shape the all-time records into the curated sections shown on the Record Book page."""

import math
from urllib.parse import urlencode

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories import records
from ssbstats_app.utils import fighter_to_filename, normalize_champ_name, stage_to_filename

TOP = 5


def _when(season, month):
    return f"S{season} M{month}"


def _span(season_from, month_from, season_to, month_to):
    if season_to is None:
        return f"{_when(season_from, month_from)} → now"
    return f"{_when(season_from, month_from)} → {_when(season_to, month_to)}"


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _ranked(entries):
    """Number entries in order, giving tied values the same rank."""
    previous = None
    for index, entry in enumerate(entries):
        key = entry.pop("sort")
        entry["rank"] = previous["rank"] if previous and previous_key == key else index + 1
        if previous and previous_key == key:
            entry["tied"] = previous["tied"] = True
        entry.setdefault("tied", False)
        previous, previous_key = entry, key
    return entries


class _Names:
    """Map the mixed-case names found in fight data (e.g. 'Rob', 'Dk') to canonical roster names."""

    def __init__(self):
        from ssbstats_app.services.content import get_autocomplete_data

        self.canonical = {name.lower(): name for name in get_autocomplete_data("fighters")}

    def __call__(self, name):
        return self.canonical.get((name or "").lower(), name)

    def fighter(self, name):
        name = self(name)
        return {"name": name, "filename": fighter_to_filename(name)}


def _entry(names, fighters, value, unit, detail, href, sort=None, badge=None, label=None):
    people = [names.fighter(f) for f in fighters]
    return {
        "fighters": people,
        "label": label or " & ".join(p["name"] for p in people),
        "value": value,
        "unit": unit,
        "detail": detail,
        "href": href,
        "badge": badge,
        "sort": value if sort is None else sort,
    }


def _fighter_href(name):
    return f"/fighter/{name}"


def _h2h_href(f1, f2):
    return "/head2head?" + urlencode({"f1": f1, "f2": f2})


def _record(key, title, blurb, entries):
    return {"key": key, "title": title, "blurb": blurb, "entries": _ranked(entries)}


def _dominance(names, latest_season):
    streaks = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "straight wins",
               _span(r["Season_Started"], r["Month_Started"], None if r["active"] else r["Season_Ended"], r["Month_Ended"]),
               _fighter_href(names(r["Fighter_Name"])), badge="Active" if r["active"] else None)
        for r in records.get_longest_win_streaks(TOP)
    ]
    elo = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "Elo",
               f"Reached {_when(r['Season'], r['Month'])}", _fighter_href(names(r["Fighter_Name"])))
        for r in records.get_peak_elo(TOP)
    ]
    best = [
        _entry(names, [r["Fighter_Name"]], f"{float(r['pct']) * 100:.1f}%", f"{r['Wins']}–{r['Losses']}",
               f"Season {r['Season']}", _fighter_href(names(r["Fighter_Name"])), sort=round(float(r["pct"]), 4),
               badge="In progress" if r["Season"] == latest_season else None)
        for r in records.get_best_seasons(TOP)
    ]
    wins = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "wins",
               f"Season {r['Season']} · {r['value']}–{r['Losses']}", _fighter_href(names(r["Fighter_Name"])),
               badge="In progress" if r["Season"] == latest_season else None)
        for r in records.get_most_season_wins(TOP)
    ]
    return {
        "key": "dominance",
        "title": "Dominance",
        "icon": "flame",
        "records": [
            _record("streak", "Longest win streak", "Consecutive wins without a loss.", streaks),
            _record("elo", "Highest Elo ever", "The peak rating each fighter has reached.", elo),
            _record("best-season", "Best season", "Highest win % in one season (15+ fights).", best),
            _record("season-wins", "Most wins in a season", "Total wins inside a single season.", wins),
        ],
    }


_MAJORS = ("Melee", "Brawl", "Ultimate")


def _won(row):
    """Short "where" for a title win: the show and stage, or how it was awarded."""
    if not row["Fight_ID"]:
        return "Inaugural champion"  # held it going into the title's first fight
    return " · ".join(part for part in (row["PPV_Name"] or "Weekly show", row["Location_Name"]) if part)


def _honor_entry(names, fighter, parts, clinch):
    """One honor-roll row: when the fighter completed it, the win that did it, and every piece."""
    return {
        **names.fighter(fighter),
        "when": _when(clinch["Season_Won"], clinch["Month_Won"]),
        "clinch_title": normalize_champ_name(clinch["Championship_Name"]),
        "clinch_where": _won(clinch),
        "href": f"/fight/{clinch['Fight_ID']}" if clinch["Fight_ID"] else _fighter_href(names(fighter)),
        "parts": [
            {"label": label, "title": normalize_champ_name(r["Championship_Name"]),
             "when": _when(r["Season_Won"], r["Month_Won"]), "where": _won(r)}
            for label, r in parts
        ],
    }


def _honors(names):
    """Triple Crown, two-major and three-major winners, in the order they completed it."""
    firsts = {}
    for row in records.get_first_title_wins():
        firsts.setdefault(row["Fighter_Name"], []).append(row)

    def chronological(rows):
        return sorted(rows, key=lambda r: (r["Season_Won"], r["Month_Won"]))

    triple, two, three = [], [], []
    for fighter, rows in firsts.items():
        by_tier = {}
        for row in chronological(rows):
            by_tier.setdefault(row["tier"], row)  # earliest reign in each tier
        if {"Major", "Minor", "Tag"} <= by_tier.keys():
            parts = chronological([by_tier["Major"], by_tier["Minor"], by_tier["Tag"]])
            triple.append(_honor_entry(names, fighter, [(r["tier"], r) for r in parts], parts[-1]))
        majors = chronological([r for r in rows if r["tier"] == "Major" and r["Championship_Name"] in _MAJORS])
        if len(majors) >= 2:
            two.append(_honor_entry(names, fighter, [("Major", r) for r in majors[:2]], majors[1]))
        if len(majors) >= 3:
            three.append(_honor_entry(names, fighter, [("Major", r) for r in majors[:3]], majors[2]))

    def ordered(entries):
        def key(e):
            season, month = e["when"][1:].split(" M")
            return int(season), int(month), e["name"]
        return sorted(entries, key=key)

    return [
        {"key": "triple-crown", "title": "Triple Crown", "icon": "crown",
         "blurb": "Won a major, a minor and a tag title.", "entries": ordered(triple)},
        {"key": "three-majors", "title": "Three-Major Winners", "icon": "gem",
         "blurb": "Won all three majors: Melee, Brawl and Ultimate.", "entries": ordered(three)},
        {"key": "two-majors", "title": "Two-Major Winners", "icon": "medal",
         "blurb": "Won two different major titles.", "entries": ordered(two)},
    ]


def _championships(names):
    reigns = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "reigns",
               f"{_plural(int(r['belts']), 'title')} · {_plural(int(r['majors']), 'major reign')}",
               _fighter_href(names(r["Fighter_Name"])))
        for r in records.get_most_title_reigns(TOP)
    ]
    defenses = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "defenses",
               f"{int(r['value']) - int(r['tag'])} singles · {int(r['tag'])} tag" if int(r["tag"]) else "All singles",
               _fighter_href(names(r["Fighter_Name"])))
        for r in records.get_most_title_defenses(TOP)
    ]
    singles = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "months",
               f"{normalize_champ_name(r['Championship_Name'])} · "
               + _span(r["Season_Won"], r["Month_Won"], None if r["active"] else r["Season_Lost"], r["Month_Lost"]),
               _fighter_href(names(r["Fighter_Name"])), badge="Champion" if r["active"] else None)
        for r in records.get_longest_singles_reigns(TOP)
    ]
    tag = []
    for r in records.get_longest_tag_reigns(TOP):
        team = r["team"].split("|")
        tag.append(_entry(names, team, int(r["value"]), "months",
                          _span(r["Season_Won"], r["Month_Won"], None if r["active"] else r["Season_Lost"], r["Month_Lost"]),
                          "/championships", badge="Champions" if r["active"] else None))
    return {
        "key": "championships",
        "title": "Championships",
        "icon": "crown",
        "honors": _honors(names),
        "records": [
            _record("reigns", "Most title reigns", "Times winning a championship (the yearly Smash Bros. trophy isn't a reign).", reigns),
            _record("defenses", "Most title defenses", "Wins as the defending champion, including Tournament and Scramble rounds.", defenses),
            _record("singles-reign", "Longest title reign", "Months holding one singles title.", singles),
            _record("tag-reign", "Longest tag team reign", "Months holding the Unified Tag titles.", tag),
        ],
    }


_TROPHIES = (
    ("tournament", "Tournament", "Tournaments"),
    ("scramble", "Scramble", "Scrambles"),
    ("mitb", "Money in the Bank", "Money in the Bank"),
    ("rumble", "Royal Rumble", "Royal Rumbles"),
    ("smash_series", "Smash Series", "Smash Series"),
    ("smash_bros", "Smash Bros. trophy", "Smash Bros. trophies"),
)


def _big_stage(names):
    ppv = [
        _entry(names, [r["Fighter_Name"]], int(r["value"]), "PPV wins",
               f"{r['value']}–{r['losses']} on pay-per-view", _fighter_href(names(r["Fighter_Name"])))
        for r in records.get_most_ppv_wins(TOP)
    ]
    trophies = []
    for r in records.get_event_trophies(TOP):
        parts = [f"{int(r[col])} {plural if int(r[col]) > 1 else single}" for col, single, plural in _TROPHIES if int(r[col])]
        trophies.append(_entry(names, [r["Fighter_Name"]], int(r["value"]), "event wins", " · ".join(parts),
                               _fighter_href(names(r["Fighter_Name"]))))
    return {
        "key": "big-stage",
        "title": "Big Stage",
        "icon": "ticket",
        "records": [
            _record("ppv-wins", "Most PPV wins", "Wins on pay-per-view cards.", ppv),
            _record("trophies", "Most marquee event wins",
                    "Tournaments, Scrambles, Money in the Bank, Royal Rumbles, Smash Series and the Smash Bros. trophy.", trophies),
        ],
    }


STAGE_MIN_FIGHTS = 8


def _wilson_bounds(wins, fights, z=1.28):
    """80% confidence interval for a win rate. Ranking by its edges keeps an 8-0 record and a
    19-5 record comparable, so small samples and busy stages (Final Destination, X5) don't dominate."""
    p = wins / fights
    center = p + z * z / (2 * fights)
    margin = z * math.sqrt(p * (1 - p) / fights + z * z / (4 * fights * fights))
    scale = 1 + z * z / fights
    return (center - margin) / scale, (center + margin) / scale


def _stages(names):
    rows = []
    for r in records.get_fighter_stage_records(STAGE_MIN_FIGHTS):
        wins, losses = int(r["Wins"]), int(r["Losses"])
        low, high = _wilson_bounds(wins, wins + losses)
        rows.append({**r, "wins": wins, "losses": losses, "low": low, "high": high})

    def pick(sort_key, reverse):
        """Top five with no stage or fighter repeated, so one busy stage can't fill the list."""
        chosen, stages, fighters = [], set(), set()
        for r in sorted(rows, key=sort_key, reverse=reverse):
            if r["Location_Name"] in stages or r["Fighter_Name"].lower() in fighters:
                continue
            stages.add(r["Location_Name"])
            fighters.add(r["Fighter_Name"].lower())
            chosen.append(r)
            if len(chosen) == TOP:
                break
        return chosen

    def entry(r, sort):
        fighter = names(r["Fighter_Name"])
        pct = r["wins"] / (r["wins"] + r["losses"]) * 100
        item = _entry(names, [fighter], f"{r['wins']}–{r['losses']}", "on this stage",
                      f"{r['Location_Name']} · {pct:.0f}%",
                      "/fights?" + urlencode({"fighter": fighter, "location": r["Location_Name"]}),
                      sort=round(sort, 4))
        item["stage"] = {"name": r["Location_Name"], "filename": stage_to_filename(r["Location_Name"])}
        return item

    best = [entry(r, r["low"]) for r in pick(lambda r: (r["low"], r["wins"]), True)]
    worst = [entry(r, -r["high"]) for r in pick(lambda r: (-r["high"], r["losses"]), True)]
    blurb = f"{STAGE_MIN_FIGHTS}+ fights there. Weighs sample size, and no stage or fighter appears twice."
    return {
        "key": "stages",
        "title": "Stages",
        "icon": "map",
        "records": [
            _record("stage-best", "Stage specialists", "Best record on a single stage. " + blurb, best),
            _record("stage-worst", "Stage nightmares", "Worst record on a single stage. " + blurb, worst),
        ],
    }


def _series_detail(names, r):
    f1, f2 = names(r["f1"]), names(r["f2"])
    w1, w2 = int(r["wins1"]), int(r["wins2"])
    if w1 == w2:
        return f"Series tied {w1}–{w2}"
    leader, high, low = (f1, w1, w2) if w1 > w2 else (f2, w2, w1)
    return f"{leader} leads {high}–{low}"


def _rivalries(names):
    most = [
        _entry(names, [r["f1"], r["f2"]], int(r["meetings"]), "meetings", _series_detail(names, r),
               _h2h_href(names(r["f1"]), names(r["f2"])), sort=(int(r["meetings"]),))
        for r in records.get_rivalries(TOP)
    ]
    lopsided = []
    for r in records.get_rivalries(TOP, min_meetings=10, order="lopsided"):
        w1, w2 = int(r["wins1"]), int(r["wins2"])
        top, bottom = (r["f1"], r["f2"]) if w1 >= w2 else (r["f2"], r["f1"])
        lopsided.append(_entry(names, [top, bottom], f"{max(w1, w2)}–{min(w1, w2)}", "series",
                               f"{_plural(int(r['meetings']), 'meeting')}", _h2h_href(names(top), names(bottom)),
                               sort=(max(w1, w2), min(w1, w2)), label=f"{names(top)} over {names(bottom)}"))
    upsets = []
    for r in records.get_biggest_upsets(TOP):
        stage = r["PPV_Name"] or "Weekly show"
        title = f" · {normalize_champ_name(r['Championship_Name'])} title" if r["Championship_Name"] else ""
        upsets.append(_entry(names, [r["winner"], r["loser"]], f"+{int(r['value'])}", "Elo gap",
                             f"{int(r['winner_elo'])} beat {int(r['loser_elo'])} · {stage}{title} · {_when(r['Season'], r['Month'])}",
                             f"/fight/{r['Fight_ID']}", sort=int(r["value"]),
                             label=f"{names(r['winner'])} over {names(r['loser'])}"))
    return {
        "key": "rivalries",
        "title": "Rivalries & Upsets",
        "icon": "swords",
        "records": [
            _record("rivalries", "Most-played rivalries", "One-on-one meetings between the same two fighters.", most),
            _record("one-sided", "Most one-sided rivalries", "Best series record with 10+ one-on-one meetings.", lopsided),
            _record("upsets", "Biggest upsets", "One-on-one wins over the highest-rated favorite, by Elo gap.", upsets),
        ],
    }


@ttl_cache(6 * 60 * 60)
def get_record_book():
    """Every record section, plus the Superstar of the Year roll. Rebuilt by the warmer when data changes."""
    names = _Names()
    latest = records.get_latest_month()
    superstars = [
        {"season": r["Season"], **names.fighter(r["Fighter_Name"])}
        for r in records.get_superstars_of_the_year()
    ]
    return {
        "sections": [_dominance(names, latest["Season"]), _championships(names), _big_stage(names), _stages(names), _rivalries(names)],
        "superstars": superstars,
        "through": _when(latest["Season"], latest["Month"]),
    }

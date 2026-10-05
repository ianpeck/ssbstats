"""The article layer of the fight page: a generated story, the numbers, the stage and the rest of the card.

Built on top of get_fight_detail_payload(), which already knows each fighter's record, streak and Elo
entering the fight. Every line here comes from the data; lines only appear when they're interesting.
"""

from concurrent.futures import ThreadPoolExecutor

from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories import fight_detail, fights, records
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.utils import event_to_slug, fighter_to_filename, serialize_value, stage_to_filename


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _names(people):
    names = [p["name"] for p in people]
    return names[0] if len(names) == 1 else " & ".join(names)


def _a(n):
    """'a' or 'an' before a spoken number (an 8%, an 11%, an 80%)."""
    return "an" if str(n).startswith("8") or str(n) in ("11", "18") else "a"


@ttl_cache(6 * 60 * 60)
def get_upset_ranks():
    """Fight ID -> rank among the league's 50 biggest one-on-one upsets by Elo gap."""
    return {row["Fight_ID"]: i + 1 for i, row in enumerate(records.get_biggest_upsets(50))}


def _title_context(fight):
    """The reign this fight started or extended, from the championship lineages."""
    if not fight["championship"]:
        return None
    title = next((t for t in get_championships_data()["titles"] if t["name"] == fight["championship"]), None)
    if title is None:
        return None
    reigns = title["reigns"]
    for i, reign in enumerate(reigns):
        if reign["won"].get("fight_id") == fight["fight_id"]:
            names = {c["name"].lower() for c in reign["champions"]}
            count = sum(1 for r in reigns[: i + 1] if {c["name"].lower() for c in r["champions"]} == names)
            return {"type": "won", "title": title, "reign": reign, "previous": reigns[i - 1] if i else None, "reign_count": count}
    # Otherwise a defending champion who kept it: which defense of the reign was this?
    when = (fight["season"], fight["month"], fight["week"] or 99, fight["fight_id"])
    defenders = [p for p in fight["participants_raw"] if p["defending"] and p["decision"] == "W"]
    if not defenders:
        return None
    lowered = {p["name"].lower() for p in defenders}
    for reign in reigns:
        if not lowered & {c["name"].lower() for c in reign["champions"]}:
            continue
        start = (reign["won"]["season"], reign["won"]["month"])
        end = (reign["lost"]["season"], reign["lost"]["month"]) if reign["lost"] else (99, 99)
        if not start <= (fight["season"], fight["month"]) <= end:
            continue
        ordinal = 0
        for f in reversed(title["fights"]):   # title fights are newest first
            f_when = (f["season"], f["month"], f["week"] or 99, f["fight_id"])
            if not start <= (f["season"], f["month"]) <= end or f_when > when:
                continue
            if any((x["name"] or "").lower() in lowered and str(x.get("defending") or "").lower() == "y"
                   and str(x.get("win") or "").lower() == "w" for x in f["fighters"]):
                ordinal += 1
        return {"type": "kept", "title": title, "reign": reign, "defense": ordinal}
    return None


def _story(fight, ctx, upset_rank):
    """Headline-worthy sentences, most important first."""
    winners = [p for p in fight["participants_raw"] if p["decision"] == "W"]
    losers = [p for p in fight["participants_raw"] if p["decision"] == "L"]
    cards = {c["name"]: c for c in fight["participants"]}
    singles = fight["layout"] == "singles"
    lines = []

    def line(icon, text, tone=""):
        lines.append({"icon": icon, "text": text, "tone": tone})

    if not winners:
        line("circle-slash", "The fight ended in a no contest.")

    # Titles
    fight_type = (fight["fight_type"] or "").lower()
    cash_in = fight_type == "cash in" and winners and losers
    if ctx and ctx["type"] == "won":
        reign, prev = ctx["reign"], ctx["previous"]
        who = reign["label"]
        if cash_in:
            text = f"{who} cashed in Money in the Bank on {_names(losers)} and won the {ctx['title']['name']} title"
        elif fight_type in ("tournament", "scramble") and fight["ppv"]:
            text = f"{who} won the {ctx['title']['name']} title in the {fight['ppv']} final"
        else:
            text = f"{who} won the {ctx['title']['name']} title"
        if ctx["reign_count"] > 1:
            text += f", {'their' if len(reign['champions']) > 1 else 'a'} {_ordinal(ctx['reign_count'])} reign with it"
        if prev and not prev["current"]:
            text += f", ending {prev['label']}'s {prev['months']}-month reign ({prev['defenses']} defense{'s' if prev['defenses'] != 1 else ''})"
        line("crown", text + ".", "gold")
    elif ctx and ctx["type"] == "kept" and ctx["defense"]:
        line("shield", f"{ctx['reign']['label']} kept the {ctx['title']['name']} title: defense #{ctx['defense']} of this reign.", "gold")

    if cash_in and not (ctx and ctx["type"] == "won"):
        if any(p["defending"] for p in winners):
            line("briefcase", f"{_names(winners)} survived {_names(losers)}'s Money in the Bank cash-in.")
        else:
            line("briefcase", f"{_names(winners)} cashed in Money in the Bank on {_names(losers)}.")
    elif fight_type == "royal rumble" and winners:
        line("trophy", f"{_names(winners)} won the Royal Rumble, outlasting {len(fight['participants_raw']) - 1} others.")
    elif fight_type == "money in the bank" and winners:
        line("briefcase", f"{_names(winners)} won a Money in the Bank briefcase.")

    # Upset
    if singles and winners and losers:
        w, l = winners[0], losers[0]
        if w.get("elo_before") is not None and l.get("elo_before") is not None:
            gap = float(l["elo_before"]) - float(w["elo_before"])
            if gap >= 75:
                chance = 1 / (1 + 10 ** (gap / 400)) * 100
                text = (f"An upset: {w['name']} entered rated {round(float(w['elo_before']))} to {l['name']}'s "
                        f"{round(float(l['elo_before']))}, about {_a(round(chance))} {chance:.0f}% chance by Elo")
                if upset_rank:
                    text += f", the {_ordinal(upset_rank)}-biggest upset in league history" if upset_rank > 1 else ", the biggest upset in league history"
                line("zap", text + ".", "hot")

    # Streaks
    # Teammates on the same streak get one line.
    by_streak = {}
    for w in winners:
        streak = cards.get(w["name"], {}).get("streak", {})
        by_streak.setdefault((streak.get("type"), streak.get("count", 0)), []).append(w)
    for (kind, count), group in by_streak.items():
        who, plural = _names(group), len(group) > 1
        if kind == "win" and count + 1 >= 3:
            line("flame", f"{who} extended {'their win streaks' if plural else 'their win streak'} to {count + 1}.")
        elif kind == "loss" and count >= 3:
            line("rotate-ccw", f"{who} snapped {'their' if plural else 'a'} {count}-fight losing streak{'s' if plural else ''}.")
    for l in losers:
        streak = cards.get(l["name"], {}).get("streak", {})
        if streak.get("type") == "win" and streak.get("count", 0) >= 3:
            line("flame-kindling", f"{_names(winners) if winners else 'The loss'} ended {l['name']}'s {streak['count']}-fight win streak.")

    # Rivalry
    mc = fight.get("matchup_context")
    if singles and mc and winners:
        f1, f2 = mc["fighter1"], mc["fighter2"]
        pre1, pre2 = mc["pre_h2h"]["fighter1_wins"], mc["pre_h2h"]["fighter2_wins"]
        post1, post2 = mc["post_h2h"]["fighter1_wins"], mc["post_h2h"]["fighter2_wins"]
        if pre1 + pre2 == 0:
            line("handshake", f"The first time {f1} and {f2} met head to head.")
        else:
            lead, trail = (f1, f2) if post1 > post2 else (f2, f1)
            hi, lo = max(post1, post2), min(post1, post2)
            if post1 == post2:
                line("scale", f"The series between {f1} and {f2} is now even at {post1}–{post2}.")
            elif (pre1 > pre2) != (post1 > post2) or pre1 == pre2:
                line("swords", f"{lead} took the lead in the series, {hi}–{lo}.")
            else:
                line("swords", f"{lead} now leads the series {hi}–{lo}.")

    # Milestones
    for w in winners:
        career = cards.get(w["name"], {}).get("career", {})
        total = career.get("wins", 0) + 1
        if total == 1:
            line("sparkles", f"{w['name']}'s first career win.", "gold")
        elif total % 25 == 0:
            line("sparkles", f"{w['name']}'s {_ordinal(total)} career win.", "gold")

    # Stage
    for w in winners[:1]:
        at = cards.get(w["name"], {}).get("location", {})
        wins, losses = at.get("wins", 0) + 1, at.get("losses", 0)
        if fight["location"] and wins + losses >= 4 and wins / (wins + losses) >= 0.7:
            line("map-pin", f"{w['name']} is now {wins}–{losses} at {fight['location']}.")

    return lines


def build_fight_extras(fight):
    """Everything the article layout adds on top of the base fight payload."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        numbers_f = pool.submit(fight_detail.get_fight_numbers, fight["season"], fight["month"], fight["week"] or 99,
                                fight["fight_id"], fight["location"] or "")
        leaders_f = pool.submit(fight_detail.get_stage_leaders, fight["location"] or "")
        card_filters = {"season": fight["season"], "month": fight["month"]}
        if fight["ppv"]:
            card_filters["ppv"] = fight["ppv"]
        else:
            card_filters.update({"week": fight["week"] or "", "brand": fight["brand"] or ""})
        card_f = pool.submit(fights.get_fight_log, card_filters, 1, 100)
        upsets_f = pool.submit(get_upset_ranks)
        numbers, leaders, card_rows, upset_ranks = numbers_f.result(), leaders_f.result(), card_f.result(), upsets_f.result()

    ctx = _title_context(fight)
    winners = [p for p in fight["participants_raw"] if p["decision"] == "W"]
    losers = [p for p in fight["participants_raw"] if p["decision"] == "L"]

    tiles = []
    for p in winners + losers:
        if p.get("elo_before") is not None and p.get("elo_after") is not None:
            delta = float(p["elo_after"]) - float(p["elo_before"])
            tiles.append({"label": f"{p['name']} Elo", "value": f"{delta:+.0f}".replace("-", "−"),
                          "sub": f"{round(float(p['elo_before']))} → {round(float(p['elo_after']))}",
                          "tone": "up" if delta > 0 else "down"})
        if len(tiles) >= 2:
            break
    if fight["layout"] == "singles" and winners and losers and winners[0].get("elo_before") is not None and losers[0].get("elo_before") is not None:
        gap = float(losers[0]["elo_before"]) - float(winners[0]["elo_before"])
        chance = 1 / (1 + 10 ** (gap / 400)) * 100
        tiles.append({"label": "Winner's pre-fight odds", "value": f"{chance:.0f}%", "sub": "by Elo", "tone": "hot" if chance < 35 else ""})
    fight_type = (fight["fight_type"] or "").lower()
    if winners and winners[0].get("match_result") not in (None, ""):
        score = winners[0]["match_result"]
        if "stock" in fight_type:
            tiles.append({"label": "Stocks left", "value": score, "sub": fight["fight_type"]})
        elif fight_type == "coin":
            tiles.append({"label": "Coins", "value": score, "sub": "winner's total"})
    if numbers.get("in_season"):
        tiles.append({"label": f"Fight of Season {fight['season']}", "value": f"#{numbers['in_season']}", "sub": f"of {numbers['season_total']}"})

    stage = None
    if fight["location"]:
        stage = {
            "name": fight["location"],
            "image": stage_to_filename(fight["location"]),
            "number": numbers.get("at_stage"),
            "total": numbers.get("stage_total"),
            "first_season": numbers.get("stage_first_season"),
            "leaders": [{"name": r["Fighter_Name"], "filename": fighter_to_filename(r["Fighter_Name"]),
                         "wins": int(r["Wins"]), "losses": int(r["Losses"])} for r in leaders],
        }

    card = [{**{k: serialize_value(v) for k, v in f.items() if k != "fighters"},
             "fighters": [{k: serialize_value(v) for k, v in x.items()} for x in f["fighters"]]}
            for f in card_rows]
    return {
        "story": _story(fight, ctx, upset_ranks.get(fight["fight_id"])),
        "tiles": tiles,
        "stage": stage,
        "card": card,
        "belt": ctx["title"]["belt"] if ctx else None,
        "title_slug": ctx["title"]["slug"] if ctx else None,
        "ppv_slug": event_to_slug(fight["ppv"]) if fight["ppv"] else None,
    }

"""Link-preview images (og:image) for fighter and fight pages, drawn on demand with Pillow.

1200x630 JPEGs: a fighter's portrait, record and titles, or a fight's stage, fighters and
result. Fonts are Oswald and Inter (SIL Open Font License, in ssbstats_app/fonts).
"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from ssbstats_app.repositories import lookups
from ssbstats_app.services.championships import get_championships_data
from ssbstats_app.services.stats import get_fight_detail_payload, get_fighter_profile_payload
from ssbstats_app.utils import fighter_to_filename, normalize_champ_name

W, H = 1200, 630
BACKGROUND = (11, 12, 16)
GOLD = (245, 184, 61)
GOLD_LIGHT = (252, 211, 77)
WHITE = (255, 255, 255)
MUTED = (150, 156, 172)
BRAND_COLORS = {"melee": (229, 72, 77), "brawl": (76, 141, 255), "ultimate": (245, 158, 11)}

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "static" / "assets"
FONTS = Path(__file__).resolve().parents[1] / "fonts"


@lru_cache(maxsize=None)
def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def _display(size):
    return _font("Oswald-Bold.ttf", size)


def _body(size, bold=False):
    return _font("Inter-Bold.ttf" if bold else "Inter-Medium.ttf", size)


@lru_cache(maxsize=None)
def _smash_ball(size):
    """The Smash Ball without its glow, as on the favicon."""
    src = Image.open(ASSETS / "other" / "smashball.png").convert("RGBA")
    cx, cy, r = 290, 287, 112
    ball = src.crop((cx - r, cy - r, cx + r, cy + r))
    mask = Image.new("L", (8 * r, 8 * r), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 8 * r - 1, 8 * r - 1), fill=255)
    ball.putalpha(ImageChops.multiply(ball.getchannel("A"), mask.resize((2 * r, 2 * r), Image.LANCZOS)))
    return ball.resize((size, size), Image.LANCZOS)


def _open(folder, stem):
    path = ASSETS / folder / f"{stem}.png"
    if not path.exists():
        return None
    im = Image.open(path).convert("RGBA")
    box = im.getbbox()
    return im.crop(box) if box else im


def _glow(card, box, color, alpha, blur):
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    card.alpha_composite(Image.merge("RGBA", (*[Image.new("L", card.size, c) for c in color], mask)))


def _vertical_fade(size, stops):
    """An RGBA black overlay whose alpha follows (position 0..1, alpha) stops top to bottom."""
    w, h = size
    column = Image.new("L", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                column.putpixel((0, y), round(a0 + (a1 - a0) * (t - t0) / max(t1 - t0, 1e-6)))
                break
    overlay = Image.new("RGBA", size, (*BACKGROUND, 0))
    overlay.putalpha(column.resize(size))
    return overlay


def _spaced(draw, xy, text, font, fill, spacing, anchor="l"):
    """Letter-spaced text (kickers). anchor 'l' starts at x, 'm' centres on x."""
    width = sum(draw.textlength(ch, font=font) for ch in text) + spacing * (len(text) - 1)
    x, y = xy
    if anchor == "m":
        x -= width / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return width


def _fit(draw, text, make_font, start, minimum, max_width):
    size = start
    while size > minimum and draw.textlength(text, font=make_font(size)) > max_width:
        size -= 2
    return make_font(size)


def _wrap(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _brandmark(card, x, y, size=40):
    card.alpha_composite(_smash_ball(size), (x, y))
    draw = ImageDraw.Draw(card)
    _spaced(draw, (x + size + 12, y + size / 2 - 15), "SSB STATS", _display(26), GOLD_LIGHT, 4)


def _jpeg(card):
    out = io.BytesIO()
    card.convert("RGB").save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out.getvalue()


# ── Fighter ─────────────────────────────────────────────────────

def fighter_card_facts(name):
    """The numbers a fighter's card shows; also its cache key and URL version."""
    profile = get_fighter_profile_payload(name)
    career = profile.get("career") or {}
    accolades = profile.get("accolades") or {}
    streaks = accolades.get("win_streaks") or []
    try:
        brand = lookups.get_fighter_brands().get(name.lower(), "")
    except Exception:
        brand = ""
    return (
        name,
        int(career.get("wins") or 0),
        int(career.get("losses") or 0),
        (profile.get("career_power_score") or {}).get("power_rank"),
        tuple(normalize_champ_name(t) for t in profile.get("current_titles") or []),
        sum(int(r.get("reign_count") or 0) for r in accolades.get("champ_reigns") or []),
        int(streaks[0]["longest_streak"]) if streaks else 0,
        len(accolades.get("awards") or []),
        (brand or "").lower(),
    )


@lru_cache(maxsize=128)
def render_fighter_card(facts):
    name, wins, losses, rank, titles, reigns, streak, awards, brand = facts
    card = Image.new("RGBA", (W, H), (*BACKGROUND, 255))
    accent = BRAND_COLORS.get(brand, GOLD)
    _glow(card, (620, -40, 1260, 640), accent, 120, 110)
    _glow(card, (-200, 380, 500, 900), GOLD, 45, 140)

    portrait = _open("fighters", fighter_to_filename(name))
    if portrait:
        portrait.thumbnail((560, 600), Image.LANCZOS)
        px = 905 - portrait.width // 2
        py = H - portrait.height + 10
        shadow = Image.new("RGBA", portrait.size, (0, 0, 0, 0))
        shadow.putalpha(portrait.getchannel("A").point(lambda a: a * 0.6))
        card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)), (px + 10, py + 14))
        card.alpha_composite(portrait, (px, py))
    card.alpha_composite(_vertical_fade((W, 120), [(0, 0), (1, 200)]), (0, H - 120))

    draw = ImageDraw.Draw(card)
    _brandmark(card, 64, 52)
    left, text_width = 66, 600
    kicker = f"#{rank} ALL-TIME" if rank else "FIGHTER"
    if brand:
        kicker += f" · {brand.upper()}"
    _spaced(draw, (left, 150), kicker, _display(30), GOLD, 3)
    name_font = _fit(draw, name.upper(), _display, 118, 56, text_width)
    draw.text((left - 2, 186), name.upper(), font=name_font, fill=WHITE)

    total = wins + losses
    record = f"{wins}–{losses}"
    record_font = _display(66)
    draw.text((left, 330), record, font=record_font, fill=GOLD_LIGHT)
    rw = draw.textlength(record, font=record_font)
    if total:
        draw.text((left + rw + 18, 362), f"{wins / total * 100:.0f}% WIN RATE", font=_body(26, bold=True), fill=MUTED)

    stats = [(str(reigns), "TITLE REIGNS"), (str(streak), "BEST STREAK"), (str(awards), "AWARDS")]
    x = left
    for value, label in stats:
        box_w = 168
        draw.rounded_rectangle((x, 436, x + box_w, 526), radius=14, fill=(20, 22, 30), outline=(46, 49, 60), width=2)
        draw.text((x + box_w / 2, 474), value, font=_display(44), fill=WHITE, anchor="mm")
        draw.text((x + box_w / 2, 508), label, font=_body(15, bold=True), fill=MUTED, anchor="mm")
        x += box_w + 14

    if titles:
        line = f"CURRENT {' & '.join(t.upper() for t in titles)} CHAMPION"
        draw.text((left, 562), line, font=_fit(draw, line, _display, 30, 20, text_width), fill=GOLD_LIGHT)
    else:
        draw.text((left, 566), "ssbstats.app", font=_body(22), fill=MUTED)
    return _jpeg(card)


# ── Fight ───────────────────────────────────────────────────────

def _cover(im, size):
    return ImageOps.fit(im.convert("RGBA"), size, Image.LANCZOS)


def _side(card, people, center_x, bottom, max_h, dim):
    """Draw up to three fighters side by side (overlapping), centred on center_x."""
    shown = people[:3]
    scale = {1: 1.0, 2: 0.82, 3: 0.68}[len(shown)] if shown else 1
    images = []
    for p in shown:
        im = _open("fighters", p["filename"])
        if im is None:
            continue
        im.thumbnail((int(360 * scale), int(max_h * scale)), Image.LANCZOS)
        if dim:
            alpha = im.getchannel("A")
            im = ImageEnhance.Brightness(ImageEnhance.Color(im).enhance(0.35)).enhance(0.55)
            im.putalpha(alpha)
        images.append(im)
    if not images:
        return
    overlap = 0.28
    total_w = sum(im.width for im in images) - sum(int(im.width * overlap) for im in images[1:])
    x = center_x - total_w // 2
    for im in images:
        card.alpha_composite(im, (x, bottom - im.height))
        x += int(im.width * (1 - overlap))


def _names(people):
    names = [p["name"] for p in people]
    if len(names) > 3:
        return f"{', '.join(names[:2])} +{len(names) - 2}"
    return " & ".join(names)


@lru_cache(maxsize=128)
def render_fight_card(fight_id):
    fight = get_fight_detail_payload(fight_id)
    if fight is None:
        return None
    card = Image.new("RGBA", (W, H), (*BACKGROUND, 255))
    stage = _open("stages", (fight.get("stage_image") or "").rsplit(".", 1)[0]) if fight.get("stage_image") else None
    if stage:
        card.alpha_composite(_cover(stage, (W, H)))
        card.alpha_composite(_vertical_fade((W, H), [(0, 225), (0.35, 120), (0.62, 150), (1, 245)]))
    else:
        _glow(card, (200, 120, 1000, 700), GOLD, 50, 140)

    _brandmark(card, 26, 24, size=30)
    draw = ImageDraw.Draw(card)
    when = [f"SEASON {fight['season']}", f"MONTH {fight['month']}"]
    if fight.get("ppv"):
        when.append(fight["ppv"].upper())
    kicker = " · ".join(when)
    size = 26
    while size > 18 and draw.textlength(kicker, font=_display(size)) + 3 * len(kicker) > 640:
        size -= 1
    _spaced(draw, (W / 2, 34 + (26 - size) / 2), kicker, _display(size), GOLD, 3, anchor="m")

    title = (fight.get("hero_title") or "").upper()
    title_font = _display(60)
    lines = _wrap(draw, title, title_font, 1040)
    if len(lines) > 2:
        title_font = _display(48)
        lines = _wrap(draw, title, title_font, 1080)[:2]
    y = 76
    for line in lines:
        draw.text((W / 2, y), line, font=title_font, fill=WHITE, anchor="ma", stroke_width=2, stroke_fill=(0, 0, 0))
        y += title_font.size + 6

    winners, losers = fight.get("winners") or [], fight.get("losers") or []
    no_winner = not winners
    left_side, right_side = (winners, losers) if not no_winner else (fight.get("participants_raw", [])[:1], fight.get("participants_raw", [])[1:])
    portrait_top = y + 18
    bottom = H - 92
    _side(card, left_side, 300, bottom, bottom - portrait_top, dim=False)
    _side(card, right_side, 900, bottom, bottom - portrait_top, dim=not no_winner)

    belt = None
    if fight.get("championship"):
        name = normalize_champ_name(fight["championship"])
        stem = next((t["belt"] for t in get_championships_data()["titles"] if t["name"] == name), None)
        belt = _open("belts", stem) if stem else None
    mid_y = (portrait_top + bottom) // 2 + 30
    if belt:
        belt.thumbnail((250, 150), Image.LANCZOS)
        card.alpha_composite(belt, (W // 2 - belt.width // 2, mid_y - belt.height - 20))
    draw.text((W / 2, mid_y + 20), "VS", font=_display(64), fill=WHITE, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))

    plate_y = H - 80
    card.alpha_composite(_vertical_fade((W, 110), [(0, 0), (0.45, 230), (1, 255)]), (0, H - 110))
    draw = ImageDraw.Draw(card)
    for people, cx, tag, color in ((left_side, 300, "WINNER" if not no_winner else "", GOLD), (right_side, 900, "DEFEATED" if not no_winner else "", MUTED)):
        if tag:
            draw.text((cx, plate_y), tag, font=_body(17, bold=True), fill=color, anchor="ma")
        label = _names(people).upper()
        draw.text((cx, plate_y + 22), label, font=_fit(draw, label, _display, 40, 22, 500), fill=WHITE, anchor="ma")
    return _jpeg(card)

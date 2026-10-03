"""Generate the browser-tab icons and the link-preview image in static/icons/.

    favicon.ico, favicon-32.png   browser tab (the Smash Ball, cropped to the ball)
    apple-touch-icon.png          iPhone/iPad home screen
    share-card.png                1200x630 preview shown when a page link is shared

Rerun after changing the Smash Ball or logo art (needs Pillow, like make_image_variants.py):

    python scripts/maintenance/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OTHER = ROOT / "static" / "assets" / "other"
OUT = ROOT / "static" / "icons"
FONTS = Path("/System/Library/Fonts/Supplemental")  # macOS; swap in any condensed bold font elsewhere

GOLD = (245, 184, 61)
BACKGROUND = (11, 12, 16)
# Portraits along the bottom of the share card.
SHARE_FIGHTERS = ["kirby", "pikachu", "toonlink", "mario", "wario", "luigi", "diddykong", "ike"]


def circle_mask(size):
    """Anti-aliased circular alpha mask."""
    big = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    return big.resize((size, size), Image.LANCZOS)


def smash_ball():
    """The Smash Ball without its glow, which turns to mush at 16-32px."""
    src = Image.open(OTHER / "smashball.png").convert("RGBA")
    cx, cy, r = 290, 287, 112
    ball = src.crop((cx - r, cy - r, cx + r, cy + r))
    ball.putalpha(ImageChops.multiply(ball.getchannel("A"), circle_mask(2 * r)))
    return ball


def make_favicons():
    ball = smash_ball()

    def icon(size, pad=0.0, background=None):
        canvas = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
        inner = round(size * (1 - 2 * pad))
        canvas.alpha_composite(ball.resize((inner, inner), Image.LANCZOS), ((size - inner) // 2, (size - inner) // 2))
        return canvas

    icon(32).save(OUT / "favicon-32.png")
    icon(48).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    icon(180, pad=0.1, background=(*BACKGROUND, 255)).convert("RGB").save(OUT / "apple-touch-icon.png")


def make_share_card():
    width, height = 1200, 630
    card = Image.new("RGBA", (width, height), (*BACKGROUND, 255))

    glow = Image.new("L", (width, height), 0)
    ImageDraw.Draw(glow).ellipse((250, -120, 950, 420), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    card.alpha_composite(Image.merge("RGBA", (*[Image.new("L", (width, height), c) for c in GOLD], glow)))

    logo = Image.open(OTHER / "supersmashbroslogo.png").convert("RGBA")
    logo = logo.crop(logo.getbbox())
    logo.thumbnail((640, 300), Image.LANCZOS)
    card.alpha_composite(logo, ((width - logo.width) // 2, 40))

    draw = ImageDraw.Draw(card)
    title_font = ImageFont.truetype(str(FONTS / "DIN Condensed Bold.ttf"), 92)
    tag_font = ImageFont.truetype(str(FONTS / "DIN Alternate Bold.ttf"), 30)

    def spaced_width(text, font, spacing):
        return sum(draw.textlength(ch, font=font) for ch in text) + spacing * (len(text) - 1)

    def spaced_text(x, y, text, font, fill, spacing):
        for ch in text:
            draw.text((x, y), ch, font=font, fill=fill)
            x += draw.textlength(ch, font=font) + spacing
        return x - spacing

    spaced_text((width - spaced_width("SSB STATS", title_font, 6)) / 2, 330, "SSB STATS", title_font, (252, 211, 77), 6)

    # Tagline words separated by gold dots (the font has no middle-dot glyph).
    words, dot_gap = ["FIGHTS", "TITLES", "RIVALRIES", "RECORDS"], 44
    x = (width - sum(spaced_width(w, tag_font, 2) for w in words) - dot_gap * (len(words) - 1)) / 2
    for i, word in enumerate(words):
        x = spaced_text(x, 425, word, tag_font, (168, 170, 184), 2)
        if i < len(words) - 1:
            cx = x + dot_gap / 2
            draw.ellipse((cx - 4, 437, cx + 4, 445), fill=GOLD)
            x += dot_gap

    size, gap = 96, 22
    mask = circle_mask(size)
    x = (width - (len(SHARE_FIGHTERS) * size + (len(SHARE_FIGHTERS) - 1) * gap)) // 2
    for name in SHARE_FIGHTERS:
        portrait = Image.open(ROOT / "static" / "assets" / "fighters" / "md" / f"{name}.webp").convert("RGBA")
        side = min(portrait.size)
        left, top = (portrait.width - side) // 2, int((portrait.height - side) * 0.15)
        portrait = portrait.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
        face = Image.new("RGBA", (size, size), (26, 29, 38, 255))
        face.alpha_composite(portrait)
        face.putalpha(mask)
        ring = Image.new("RGBA", (size + 6, size + 6), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, size + 5, size + 5), fill=(*GOLD, 200))
        card.alpha_composite(ring, (x - 3, 497))
        card.alpha_composite(face, (x, 500))
        x += size + gap

    card.convert("RGB").save(OUT / "share-card.png", optimize=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    make_favicons()
    make_share_card()
    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()

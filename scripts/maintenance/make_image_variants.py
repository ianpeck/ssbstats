"""Generate web-sized WebP copies of the site's large images.

The originals in static/assets/<folder>/ are 1-4 MB each and were being loaded even
for 30px icons. This writes two resized copies next to them:

    static/assets/<folder>/sm/<name>.webp   icons and thumbnails
    static/assets/<folder>/md/<name>.webp   cards, page headers and heroes

Originals are never modified. Pages fall back to the original automatically if a copy
is missing (see the image fallback script in templates/base.html), but rerun this after
adding new fighters, stages, belts or PPV art:

    pip install pillow   # only needed for this script, not for the site
    python scripts/maintenance/make_image_variants.py
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[2] / "static" / "assets"

# Longest side in pixels for each size, chosen to stay sharp on 2x (retina) screens.
SIZES = {
    "fighters": {"sm": 128, "md": 640},
    "stages": {"sm": 320, "md": 1280},
    "belts": {"sm": 192, "md": 720},
    "ppv": {"sm": 480, "md": 1200},
}
SOURCE_EXTENSIONS = (".png", ".jpeg", ".jpg")
QUALITY = 82


def resize(src, dest, longest_side):
    """Write a WebP copy of src whose longest side is at most longest_side."""
    with Image.open(src) as image:
        image = image.convert("RGBA") if image.mode in ("P", "LA", "RGBA") else image.convert("RGB")
        image.thumbnail((longest_side, longest_side), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest, "WEBP", quality=QUALITY, method=6)


def main():
    total_before = total_after = written = 0
    for folder, sizes in SIZES.items():
        sources = {}
        # When a name exists as both .png and .jpeg, the site references the .png.
        for path in sorted((ASSETS / folder).iterdir()):
            if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
                if path.stem not in sources or path.suffix.lower() == ".png":
                    sources[path.stem] = path
        for stem, src in sources.items():
            total_before += src.stat().st_size
            for size, longest in sizes.items():
                dest = ASSETS / folder / size / f"{stem}.webp"
                if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                    resize(src, dest, longest)
                    written += 1
                total_after += dest.stat().st_size
        print(f"{folder}: {len(sources)} images")
    print(f"Wrote {written} files. Originals {total_before / 1e6:.0f} MB -> copies {total_after / 1e6:.1f} MB (both sizes)")


if __name__ == "__main__":
    main()

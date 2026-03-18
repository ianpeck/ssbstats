from decimal import Decimal
import unicodedata


_STAGE_OVERRIDES = {
    "mushroom kingdom ii": "mushroomkingdom2",
}


def serialize_value(val):
    """Convert database values into JSON-safe Python primitives."""
    if isinstance(val, Decimal):
        return float(val)
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def fighter_to_filename(name):
    """Map a fighter name to the corresponding asset filename stem."""
    overrides = {
        "banjo & kazooie": "banjoandkazooie",
        "banjo and kazooie": "banjoandkazooie",
    }
    lower = name.lower()
    if lower in overrides:
        return overrides[lower]
    return lower.replace(" ", "").replace(".", "").replace("&", "and")


def stage_to_filename(name):
    """Map a stage name to the corresponding asset filename stem."""
    lower = name.lower()
    if lower in _STAGE_OVERRIDES:
        return _STAGE_OVERRIDES[lower]
    normalized = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode("ascii")
    return normalized.lower().replace(" ", "").replace(",", "").replace("'", "").replace("(", "").replace(")", "").replace("-", "").replace(".", "")


def event_to_slug(name):
    """Map an event name to a stable URL slug."""
    return stage_to_filename(name or "")


def normalize_champ_name(value):
    """Normalize championship names for cleaner display in the UI."""
    if value is None:
        return value
    return str(value).replace("Unified Tag 1", "Unified Tag")

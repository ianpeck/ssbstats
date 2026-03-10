import os

import yaml

from ssbstats_app.repositories import lookups


_AUTOCOMPLETE_CACHE = {}
_YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fighters.yaml")


def get_fighter_blurb(name):
    """Load a fighter blurb from YAML using tolerant name matching."""
    try:
        with open(_YAML_PATH, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        blurb = data.get(name)
        if blurb is None:
            lower = name.lower()
            blurb = next((value for key, value in data.items() if key.lower() == lower), None)
        if blurb is None:
            normalized = name.lower().replace(".", "")
            blurb = next((value for key, value in data.items() if key.lower().replace(".", "") == normalized), None)
        return blurb or {}
    except Exception:
        return {}


def get_autocomplete_data(category):
    """Return cached autocomplete options for the requested category."""
    if category not in _AUTOCOMPLETE_CACHE:
        loaders = {
            "fighters": lookups.get_all_fighters,
            "locations": lookups.get_all_locations,
            "fight_types": lookups.get_all_fight_types,
            "ppvs": lookups.get_all_ppv_names,
            "championships": lookups.get_all_championships,
            "brands": lookups.get_all_brands,
        }
        if category in loaders:
            try:
                _AUTOCOMPLETE_CACHE[category] = loaders[category]()
            except Exception:
                _AUTOCOMPLETE_CACHE[category] = []
    return _AUTOCOMPLETE_CACHE.get(category, [])

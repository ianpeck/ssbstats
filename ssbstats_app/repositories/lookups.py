from ssbstats_app.cache import ttl_cache
from ssbstats_app.repositories.base import nk, select_list, select_view_dicts


def get_all_fighters():
    """Return every fighter name for autocomplete and roster views."""
    return select_list("SELECT * FROM Fighter", 0)


def get_canonical_name_map():
    """Return lowercase-to-canonical fighter name mappings."""
    rows = select_list("SELECT Fighter_Name FROM Fighter", 0)
    return {name.lower(): name for name in rows if name}


def get_all_locations():
    """Return every location name for autocomplete and filters."""
    return select_list("SELECT * FROM Location", 1)


def get_all_fight_types():
    """Return every fight type description for autocomplete and filters."""
    return select_list("SELECT * FROM FightType", 1)


def get_all_ppv_names():
    """Return every PPV name for autocomplete and filters."""
    return select_list("SELECT * FROM PPV", 1)


def get_all_championships():
    """Return every championship name for autocomplete and filters."""
    return select_list("SELECT * FROM Championship", 1)


def get_all_brands():
    """Return every brand name for autocomplete and filters."""
    return select_list("SELECT * FROM Brand", 1)


def get_latest_season():
    """Return the most recent season ID."""
    rows = select_list("SELECT MAX(Season_ID) FROM Season", 0)
    return int(rows[0]) if rows else 0


def get_current_champions():
    """Return current championships keyed by lowercase fighter name."""
    rows = select_view_dicts("SELECT * FROM CurrentChampions")
    result = {}
    for row in rows:
        result.setdefault(nk(row["Fighter_Name"]), []).append(row["Championship_Name"])
    return result


@ttl_cache(6 * 60 * 60)
def get_fighter_brands():
    """Return each fighter's current brand, keyed by lowercase fighter name.

    Derived from fights rather than Fighter.Brand_ID (which isn't updated after drafts):
    the brand of the fighter's most recent branded fight, so the current season wins and
    inactive fighters fall back to the last brand they fought on.
    """
    rows = select_view_dicts(
        """
        SELECT Fighter_Name, Brand_Name
        FROM (
            SELECT Fighter_Name, Brand_Name,
                   ROW_NUMBER() OVER (
                       PARTITION BY Fighter_Name
                       ORDER BY Season DESC, Month DESC, COALESCE(Week, 99) DESC, Fight_ID DESC
                   ) AS rn
            FROM FightLog
            WHERE Brand_Name IS NOT NULL
        ) latest
        WHERE rn = 1
        """
    )
    return {nk(row["Fighter_Name"]): row["Brand_Name"] or "" for row in rows}

from ssbstats_app.repositories.base import select_view_dicts
from ssbstats_app.repositories.lookups import get_canonical_name_map


def get_fight_log(filters, page=1, per_page=100):
    """Return paginated fight-log entries grouped by fight and filtered by criteria."""
    conditions = []
    params = []
    canonical_names = get_canonical_name_map()
    mapping = [
        ("season", "Season", False),
        ("month", "Month", False),
        ("fight_type", "Description", False),
        ("location", "Location_Name", False),
        ("ppv", "PPV_Name", False),
        ("championship", "Championship_Name", False),
        ("fighter", "Fighter_Name", True),
        ("brand", "Brand_Name", False),
        ("decision", "Decision", False),
        ("contender", "Contender_Indicator", False),
        ("fight_id", "Fight_ID", False),
    ]
    for key, col, use_like in mapping:
        val = filters.get(key, "")
        if val:
            if use_like:
                canonical = canonical_names.get(str(val).strip().lower())
                if canonical:
                    conditions.append(f"{col} = %s")
                    params.append(canonical)
                else:
                    conditions.append(f"{col} LIKE %s")
                    params.append(f"%{val}%")
            else:
                conditions.append(f"{col} = %s")
                params.append(val)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page
    sql = f"""
        SELECT fl.*
        FROM FightLog fl
        INNER JOIN (
            SELECT DISTINCT Fight_ID
            FROM FightLog {where}
            ORDER BY Season DESC, Month DESC, COALESCE(Week, 99) DESC, Fight_ID DESC
            LIMIT %s OFFSET %s
        ) ids ON fl.Fight_ID = ids.Fight_ID
        ORDER BY fl.Season DESC, fl.Month DESC, COALESCE(fl.Week, 99) DESC, fl.Fight_ID DESC,
                 fl.Decision DESC, fl.Fighter_Name
    """
    rows = select_view_dicts(sql, params + [per_page, offset])

    fights = {}
    fight_order = []
    for row in rows:
        fid = row.get("Fight_ID")
        if fid not in fights:
            fights[fid] = {
                "fight_id": fid,
                "season": row.get("Season"),
                "month": row.get("Month"),
                "week": row.get("Week"),
                "ppv": row.get("PPV_Name"),
                "location": row.get("Location_Name"),
                "fight_type": row.get("Description"),
                "championship": row.get("Championship_Name"),
                "brand": row.get("Brand_Name"),
                "fighters": [],
            }
            fight_order.append(fid)
        fights[fid]["fighters"].append(
            {
                "name": row.get("Fighter_Name"),
                "win": row.get("Decision"),
                "match_result": row.get("Match_Result"),
                "seed": row.get("Seed"),
                "defending": row.get("DefendingIndicator"),
                "contender": row.get("Contender_Indicator"),
            }
        )
    return [fights[fid] for fid in fight_order]

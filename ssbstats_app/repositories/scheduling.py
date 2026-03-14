from collections import defaultdict

from ssbstats_app.repositories.base import get_connection, get_write_connection, select_view_dicts


def get_booking_context():
    """Return the current booking window and dimension lookups for scheduling."""
    brand_rows = select_view_dicts(
        """
        SELECT
            f.Brand_ID,
            MAX(f.Season_ID * 10000 + f.Month * 100 + f.Week) AS window_key
        FROM Fight f
        WHERE f.Brand_ID IS NOT NULL
        GROUP BY f.Brand_ID
        """
    )
    brandless_rows = select_view_dicts(
        """
        SELECT MAX(f.Season_ID * 10000 + f.Month * 100 + f.Week) AS window_key
        FROM Fight f
        WHERE f.Brand_ID IS NULL
        """
    )

    if brand_rows:
        window_keys = [int(row["window_key"]) for row in brand_rows if row["window_key"] is not None]
        shared_brand_key = min(window_keys) if window_keys else 10101
        brandless_key = int(brandless_rows[0]["window_key"]) if brandless_rows and brandless_rows[0]["window_key"] is not None else None
        anchor_key = brandless_key if brandless_key and brandless_key > shared_brand_key else shared_brand_key
        season_id = anchor_key // 10000
        month = (anchor_key % 10000) // 100
        week = anchor_key % 100
        if week >= 4:
            month += 1
            week = 1
        else:
            week += 1
    else:
        season_id = 1
        month = 1
        week = 1
    lookups = {
        "brands": select_view_dicts("SELECT Brand_ID, Brand_Name FROM Brand ORDER BY Brand_ID"),
        "locations": select_view_dicts("SELECT Location_ID, Location_Name FROM Location ORDER BY Location_Name"),
        "fight_types": select_view_dicts("SELECT FightType_ID, Description FROM FightType ORDER BY FightType_ID"),
        "championships": select_view_dicts("SELECT Championship_ID, Championship_Name FROM Championship ORDER BY Championship_Name"),
        "ppvs": select_view_dicts("SELECT PPV_ID, PPV_Name FROM PPV ORDER BY PPV_Name"),
        "fighters": select_view_dicts("SELECT Fighter_Name, Brand_ID FROM Fighter ORDER BY Fighter_Name"),
    }
    return {
        "season_id": season_id,
        "month": month,
        "week": week,
        **lookups,
    }


def get_scheduled_matches_for_window(season_id, month, week):
    """Return scheduled matches and participant rows for the requested booking window."""
    rows = select_view_dicts(
        """
        SELECT
            sm.scheduled_match_id,
            sm.season_id,
            sm.month,
            sm.week,
            sm.brand_id,
            b.Brand_Name,
            sm.match_order,
            sm.scheduled_start_at,
            sm.location_id,
            l.Location_Name,
            sm.ppv_id,
            p.PPV_Name,
            sm.championship_id,
            c.Championship_Name,
            sm.fight_type_id,
            ft.Description AS FightType_Description,
            sm.contender_indicator,
            sm.status,
            sm.fight_id,
            sm.notes,
            smp.scheduled_match_participant_id,
            smp.slot_number,
            smp.fighter_name,
            smp.team_id,
            smp.team_color,
            smp.cpu_level,
            smp.cpu_level_source,
            smp.seed,
            smp.defending_indicator
        FROM scheduled_matches sm
        JOIN Brand b ON sm.brand_id = b.Brand_ID
        JOIN Location l ON sm.location_id = l.Location_ID
        JOIN FightType ft ON sm.fight_type_id = ft.FightType_ID
        LEFT JOIN PPV p ON sm.ppv_id = p.PPV_ID
        LEFT JOIN Championship c ON sm.championship_id = c.Championship_ID
        LEFT JOIN scheduled_match_participants smp ON sm.scheduled_match_id = smp.scheduled_match_id
        WHERE sm.season_id = %s AND sm.month = %s AND sm.week = %s
        ORDER BY sm.brand_id, sm.match_order, sm.scheduled_match_id, smp.slot_number
        """,
        (season_id, month, week),
    )
    matches = {}
    ordered_ids = []
    for row in rows:
        match_id = row["scheduled_match_id"]
        if match_id not in matches:
            matches[match_id] = {
                "scheduled_match_id": match_id,
                "season_id": row["season_id"],
                "month": row["month"],
                "week": row["week"],
                "brand_id": row["brand_id"],
                "brand_name": row["Brand_Name"],
                "match_order": row["match_order"],
                "scheduled_start_at": row["scheduled_start_at"],
                "location_id": row["location_id"],
                "location_name": row["Location_Name"],
                "ppv_id": row["ppv_id"],
                "ppv_name": row["PPV_Name"],
                "championship_id": row["championship_id"],
                "championship_name": row["Championship_Name"],
                "fight_type_id": row["fight_type_id"],
                "fight_type_description": row["FightType_Description"],
                "contender_indicator": bool(row["contender_indicator"]),
                "status": row["status"],
                "fight_id": row["fight_id"],
                "notes": row["notes"],
                "participants": [],
            }
            ordered_ids.append(match_id)
        if row["scheduled_match_participant_id"] is not None:
            matches[match_id]["participants"].append(
                {
                    "scheduled_match_participant_id": row["scheduled_match_participant_id"],
                    "slot_number": row["slot_number"],
                    "fighter_name": row["fighter_name"],
                    "team_id": row["team_id"],
                    "team_color": row["team_color"],
                    "cpu_level": row["cpu_level"],
                    "cpu_level_source": row["cpu_level_source"],
                    "seed": row["seed"],
                    "defending_indicator": bool(row["defending_indicator"]),
                }
            )
    return [matches[match_id] for match_id in ordered_ids]


def create_scheduled_match(payload):
    """Insert a scheduled match and its participants using the write connection."""
    conn = get_write_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduled_matches (
                    season_id,
                    month,
                    week,
                    brand_id,
                    match_order,
                    scheduled_start_at,
                    location_id,
                    ppv_id,
                    championship_id,
                    fight_type_id,
                    contender_indicator,
                    status,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued', %s)
                """,
                (
                    payload["season_id"],
                    payload["month"],
                    payload["week"],
                    payload["brand_id"],
                    payload["match_order"],
                    payload.get("scheduled_start_at") or None,
                    payload["location_id"],
                    payload.get("ppv_id") or None,
                    payload.get("championship_id") or None,
                    payload["fight_type_id"],
                    1 if payload.get("contender_indicator") else 0,
                    payload.get("notes") or None,
                ),
            )
            scheduled_match_id = cur.lastrowid
            for participant in payload["participants"]:
                cur.execute(
                    """
                    INSERT INTO scheduled_match_participants (
                        scheduled_match_id,
                        slot_number,
                        fighter_name,
                        team_id,
                        team_color,
                        cpu_level,
                        cpu_level_source,
                        seed,
                        defending_indicator
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        scheduled_match_id,
                        participant["slot_number"],
                        participant["fighter_name"],
                        participant.get("team_id") or None,
                        participant.get("team_color") or None,
                        participant["cpu_level"],
                        participant.get("cpu_level_source") or "manual",
                        participant.get("seed") or None,
                        1 if participant.get("defending_indicator") else 0,
                    ),
                )
        conn.commit()
        return scheduled_match_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_scheduled_match(payload):
    """Update a scheduled match and fully replace its participant rows."""
    conn = get_write_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_matches
                SET
                    season_id = %s,
                    month = %s,
                    week = %s,
                    brand_id = %s,
                    match_order = %s,
                    scheduled_start_at = %s,
                    location_id = %s,
                    ppv_id = %s,
                    championship_id = %s,
                    fight_type_id = %s,
                    contender_indicator = %s,
                    notes = %s
                WHERE scheduled_match_id = %s
                """,
                (
                    payload["season_id"],
                    payload["month"],
                    payload["week"],
                    payload["brand_id"],
                    payload["match_order"],
                    payload.get("scheduled_start_at") or None,
                    payload["location_id"],
                    payload.get("ppv_id") or None,
                    payload.get("championship_id") or None,
                    payload["fight_type_id"],
                    1 if payload.get("contender_indicator") else 0,
                    payload.get("notes") or None,
                    payload["scheduled_match_id"],
                ),
            )
            cur.execute(
                "DELETE FROM scheduled_match_participants WHERE scheduled_match_id = %s",
                (payload["scheduled_match_id"],),
            )
            for participant in payload["participants"]:
                cur.execute(
                    """
                    INSERT INTO scheduled_match_participants (
                        scheduled_match_id,
                        slot_number,
                        fighter_name,
                        team_id,
                        team_color,
                        cpu_level,
                        cpu_level_source,
                        seed,
                        defending_indicator
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payload["scheduled_match_id"],
                        participant["slot_number"],
                        participant["fighter_name"],
                        participant.get("team_id") or None,
                        participant.get("team_color") or None,
                        participant["cpu_level"],
                        participant.get("cpu_level_source") or "manual",
                        participant.get("seed") or None,
                        1 if participant.get("defending_indicator") else 0,
                    ),
                )
        conn.commit()
        return payload["scheduled_match_id"]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_scheduled_match(scheduled_match_id):
    """Delete a scheduled match and its participant rows."""
    conn = get_write_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scheduled_match_participants WHERE scheduled_match_id = %s", (scheduled_match_id,))
            cur.execute("DELETE FROM scheduled_matches WHERE scheduled_match_id = %s", (scheduled_match_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_next_match_order(season_id, month, week, brand_id):
    """Return the next match order for the active booking window/brand."""
    rows = select_view_dicts(
        """
        SELECT COALESCE(MAX(match_order), 0) AS max_match_order
        FROM scheduled_matches
        WHERE season_id = %s AND month = %s AND week = %s AND brand_id = %s
        """,
        (season_id, month, week, brand_id),
    )
    return int(rows[0]["max_match_order"] or 0) + 1


def group_matches_by_brand(matches):
    """Group scheduled matches by brand id for page rendering."""
    grouped = defaultdict(list)
    for match in matches:
        if match["brand_id"] is not None:
            grouped[match["brand_id"]].append(match)
    return grouped

from ssbstats_app.repositories import scheduling


def get_schedule_admin_payload():
    """Build the payload for the local schedule admin page."""
    context = scheduling.get_booking_context()
    matches = scheduling.get_scheduled_matches_for_window(context["season_id"], context["month"], context["week"])
    matches_by_brand = scheduling.group_matches_by_brand(matches)
    brands = []
    default_location = context["locations"][0] if context["locations"] else {"Location_ID": "", "Location_Name": ""}
    for brand in context["brands"]:
        brand_id = int(brand["Brand_ID"])
        next_match_order = scheduling.get_next_match_order(context["season_id"], context["month"], context["week"], brand_id)
        brand_matches = matches_by_brand.get(brand_id, [])
        show_location_id = brand_matches[0]["location_id"] if brand_matches else default_location["Location_ID"]
        show_location_name = brand_matches[0]["location_name"] if brand_matches else default_location["Location_Name"]
        show_ppv_id = brand_matches[0]["ppv_id"] if brand_matches else ""
        show_ppv_name = brand_matches[0]["ppv_name"] if brand_matches and brand_matches[0]["ppv_name"] else ""
        brands.append(
            {
                "brand_id": brand_id,
                "brand_name": brand["Brand_Name"],
                "next_match_order": next_match_order,
                "show_location_id": show_location_id,
                "show_location_name": show_location_name,
                "show_ppv_id": show_ppv_id,
                "show_ppv_name": show_ppv_name,
                "default_slots": [
                    {
                        "slot_index": slot_index,
                        "match_order": next_match_order + slot_index - 1,
                        "label": "Main Event" if slot_index == 5 else f"Match {slot_index}",
                    }
                    for slot_index in range(1, 6)
                ],
                "matches": brand_matches,
            }
        )
    return {
        "active_window": {
            "season_id": context["season_id"],
            "month": context["month"],
            "week": context["week"],
            "is_ppv_week": context["week"] == 4,
        },
        "brands": brands,
        "ppv_matches": [match for match in matches if match["brand_id"] is None],
        "lookups": {
            "locations": context["locations"],
            "fight_types": context["fight_types"],
            "championships": context["championships"],
            "ppvs": context["ppvs"],
            "fighters": context["fighters"],
            "tag_team_fight_type_id": next(
                (int(row["FightType_ID"]) for row in context["fight_types"] if (row["Description"] or "").lower() == "tag team"),
                None,
            ),
        },
    }


def _build_match_payload(form_data):
    """Normalize submitted form fields into a scheduled match payload."""
    participant_total = int(form_data.get("participant_count", 0) or 0)
    participants = []
    for index in range(1, participant_total + 1):
        fighter_name = (form_data.get(f"fighter_name_{index}") or "").strip()
        if not fighter_name:
            continue
        participants.append(
            {
                "slot_number": index,
                "fighter_name": fighter_name,
                "team_id": (form_data.get(f"team_id_{index}") or "").strip() or None,
                "team_color": (form_data.get(f"team_color_{index}") or "").strip() or None,
                "cpu_level": int(form_data.get(f"cpu_level_{index}") or 9),
                "cpu_level_source": (form_data.get(f"cpu_level_source_{index}") or "manual").strip(),
                "seed": (form_data.get(f"seed_{index}") or "").strip() or None,
                "defending_indicator": form_data.get(f"defending_indicator_{index}") == "on",
            }
        )
    payload = {
        "season_id": int(form_data["season_id"]),
        "month": int(form_data["month"]),
        "week": int(form_data["week"]),
        "brand_id": int(form_data["brand_id"]),
        "match_order": int(form_data["match_order"]),
        "scheduled_start_at": None,
        "location_id": int(form_data["location_id"]),
        "ppv_id": (form_data.get("ppv_id") or "").strip() or None,
        "championship_id": (form_data.get("championship_id") or "").strip() or None,
        "fight_type_id": int(form_data["fight_type_id"]),
        "contender_indicator": form_data.get("contender_indicator") == "on",
        "notes": (form_data.get("notes") or "").strip() or None,
        "participants": participants,
    }
    payload["ppv_id"] = int(payload["ppv_id"]) if payload["ppv_id"] else None
    payload["championship_id"] = int(payload["championship_id"]) if payload["championship_id"] else None
    return payload


def create_scheduled_match_from_form(form_data):
    """Persist a new scheduled match from submitted form fields."""
    return scheduling.create_scheduled_match(_build_match_payload(form_data))


def update_scheduled_match_from_form(form_data):
    """Update an existing scheduled match from submitted form fields."""
    payload = _build_match_payload(form_data)
    payload["scheduled_match_id"] = int(form_data["scheduled_match_id"])
    return scheduling.update_scheduled_match(payload)


def delete_scheduled_match_from_form(form_data):
    """Delete an existing scheduled match by row id."""
    return scheduling.delete_scheduled_match(int(form_data["scheduled_match_id"]))

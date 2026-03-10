from flask import Blueprint, jsonify, request

from ssbstats_app.repositories.seasons import get_all_seasons
from ssbstats_app.services.chat import answer_question
from ssbstats_app.services.content import get_autocomplete_data
from ssbstats_app.services.stats import (
    get_championships_payload,
    get_compare_payload,
    get_events_payload,
    get_fight_log_payload,
    get_fighter_advanced_payload,
    get_fighter_profile_payload,
    get_head_to_head,
    get_leaderboard_payload,
    get_season_payload,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/autocomplete/<category>")
def autocomplete(category):
    """Return autocomplete results for a supported lookup category."""
    data = get_autocomplete_data(category)
    query = request.args.get("q", "").lower()
    if query:
        data = [item for item in data if query in item.lower()]
    return jsonify(data)


@api_bp.route("/head2head", methods=["POST"])
def head_to_head():
    """Return filtered head-to-head stats for two fighters."""
    data = request.get_json() or {}
    fighter1 = data.get("fighter1", "")
    fighter2 = data.get("fighter2", "")
    if not fighter1 or not fighter2:
        return jsonify({"error": "Both fighters are required"}), 400
    filters = {
        "map": data.get("map", ""),
        "matchType": data.get("matchType", ""),
        "season": data.get("season", ""),
        "month": data.get("month", ""),
        "ppv": data.get("ppv", ""),
        "championship": data.get("championship", ""),
        "contender": data.get("contender", ""),
        "brand": data.get("brand", ""),
    }
    try:
        return jsonify(get_head_to_head(fighter1, fighter2, filters))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/fighter/<name>")
def fighter(name):
    """Return the full fighter profile payload as JSON."""
    try:
        return jsonify(get_fighter_profile_payload(name))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/fighter/<name>/advanced")
def fighter_advanced(name):
    """Return advanced fighter analytics payloads for charts and streaks."""
    try:
        return jsonify(get_fighter_advanced_payload(name))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/leaderboard")
def leaderboard():
    """Return leaderboard data for all time or a specific season."""
    season = request.args.get("season", "")
    try:
        return jsonify(get_leaderboard_payload(season))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/seasons")
def seasons():
    """Return the list of available seasons."""
    try:
        return jsonify(get_all_seasons())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/season/<int:season_id>")
def season(season_id):
    """Return the full payload for a specific season page."""
    try:
        return jsonify(get_season_payload(season_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/fights")
def fights():
    """Return paginated fight log results using the supplied filters."""
    filters = {
        "season": request.args.get("season", ""),
        "month": request.args.get("month", ""),
        "fight_type": request.args.get("fight_type", ""),
        "location": request.args.get("location", ""),
        "ppv": request.args.get("ppv", ""),
        "championship": request.args.get("championship", ""),
        "fighter": request.args.get("fighter", ""),
        "brand": request.args.get("brand", ""),
        "decision": request.args.get("decision", ""),
        "fight_id": request.args.get("fight_id", ""),
    }
    page = int(request.args.get("page", 1))
    try:
        return jsonify(get_fight_log_payload(filters, page))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/compare", methods=["POST"])
def compare():
    """Return the comparison payload for two fighters."""
    data = request.get_json() or {}
    fighter1 = (data.get("fighter1") or "").strip()
    fighter2 = (data.get("fighter2") or "").strip()
    if not fighter1 or not fighter2:
        return jsonify({"error": "Both fighters required"}), 400
    try:
        return jsonify(get_compare_payload(fighter1, fighter2))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/championships")
def championships():
    """Return championship history and current season metadata."""
    try:
        return jsonify(get_championships_payload())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/events")
def events():
    """Return PPV and event history rows."""
    try:
        return jsonify(get_events_payload())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/chat", methods=["POST"])
def chat():
    """Return an AI-generated answer for a natural-language stats question."""
    payload = request.get_json(silent=True) or {}
    result = answer_question(payload.get("question", ""), payload.get("history", []))
    status = result.pop("status", 200)
    return jsonify(result), status

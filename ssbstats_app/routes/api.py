from flask import Blueprint, jsonify, request

from ssbstats_app.repositories import lookups
from ssbstats_app.repositories.seasons import get_all_seasons
from ssbstats_app.security import DailyQuota, RateLimiter, admin_ips, get_client_ip
from ssbstats_app.services.chat import answer_question

from ssbstats_app.services.content import get_autocomplete_data
from ssbstats_app.services.search import get_search_index
from ssbstats_app.services.stats import (
    get_championships_payload,
    get_compare_payload,
    get_fight_detail_payload,
    get_events_payload,
    get_fight_log_payload,
    get_fighter_advanced_payload,
    get_fighter_profile_payload,
    get_head_to_head,
    get_leaderboard_payload,
    get_season_payload,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")
_chat_limiter = RateLimiter(limit=5, window_seconds=60)  # per visitor IP, per worker
_chat_daily = DailyQuota(per_visitor=40, total=100)  # shared across workers; resets midnight Eastern
_DAILY_LIMIT_MESSAGES = {
    "visitor": "You've asked 40 questions today, which is the daily limit. The stats AI resets at midnight Eastern, so come back tomorrow!",
    "total": "The stats AI has answered its 100 questions for today. It resets at midnight Eastern, so check back tomorrow!",
}


@api_bp.route("/autocomplete/<category>")
def autocomplete(category):
    """Return autocomplete results for a supported lookup category."""
    data = get_autocomplete_data(category)
    query = request.args.get("q", "").lower()
    if query:
        data = [item for item in data if query in item.lower()]
    return jsonify(data)


@api_bp.route("/search-index")
def search_index():
    """Everything the site-wide search can find; the browser filters it locally."""
    response = jsonify(get_search_index())
    response.headers["Cache-Control"] = "public, max-age=600"
    return response


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


def _canonical_fighter(name):
    """Return the fighter's canonical spelling, or None if unknown.

    Unknown names get a 404 instead of an empty payload, so they never enter the cache.
    If the fighter list couldn't load, the name is passed through unchanged.
    """
    known = {fighter.lower(): fighter for fighter in get_autocomplete_data("fighters")}
    if not known:
        return name
    return known.get(name.lower())


@api_bp.route("/fighter/<name>")
def fighter(name):
    """Return the full fighter profile payload as JSON."""
    name = _canonical_fighter(name)
    if not name:
        return jsonify({"error": "Fighter not found"}), 404
    try:
        return jsonify(get_fighter_profile_payload(name))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/fighter/<name>/advanced")
def fighter_advanced(name):
    """Return advanced fighter analytics payloads for charts and streaks."""
    name = _canonical_fighter(name)
    if not name:
        return jsonify({"error": "Fighter not found"}), 404
    try:
        return jsonify(get_fighter_advanced_payload(name))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/leaderboard")
def leaderboard():
    """Return leaderboard data for all time or a specific season."""
    season = request.args.get("season", "").strip()
    # Only real seasons reach the cache, so junk query strings can't grow it.
    if season and not (season.isdigit() and 1 <= int(season) <= lookups.get_latest_season()):
        return jsonify({"error": "Unknown season"}), 404
    try:
        return jsonify(get_leaderboard_payload(str(int(season)) if season else ""))
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
    if not 1 <= season_id <= lookups.get_latest_season():
        return jsonify({"error": "Unknown season"}), 404
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
        "week": request.args.get("week", ""),
        "fight_type": request.args.get("fight_type", ""),
        "location": request.args.get("location", ""),
        "ppv": request.args.get("ppv", ""),
        "championship": request.args.get("championship", ""),
        "fighter": request.args.get("fighter", ""),
        "fighter2": request.args.get("fighter2", ""),
        "fighter3": request.args.get("fighter3", ""),
        "fighter4": request.args.get("fighter4", ""),
        "fighter_op2": request.args.get("fighter_op2", "or"),
        "fighter_op3": request.args.get("fighter_op3", "or"),
        "fighter_op4": request.args.get("fighter_op4", "or"),
        "brand": request.args.get("brand", ""),
        "decision": request.args.get("decision", ""),
        "contender": request.args.get("contender", ""),
        "fight_id": request.args.get("fight_id", ""),
    }
    page = int(request.args.get("page", 1))
    try:
        return jsonify(get_fight_log_payload(filters, page))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/fight/<int:fight_id>")
def fight_detail(fight_id):
    """Return the full payload for a dedicated fight detail page."""
    try:
        payload = get_fight_detail_payload(fight_id)
        if payload is None:
            return jsonify({"error": "Fight not found"}), 404
        return jsonify(payload)
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
    names = [_canonical_fighter(fighter1), _canonical_fighter(fighter2)]
    if not all(names):
        missing = fighter1 if not names[0] else fighter2
        return jsonify({"error": f"No fighter named \"{missing}\""}), 404
    if names[0] == names[1]:
        return jsonify({"error": "Pick two different fighters"}), 400
    try:
        return jsonify(get_compare_payload(*names))
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
    ip = get_client_ip()
    if ip not in admin_ips():
        if _chat_limiter.hit():
            return jsonify({"answer": "You're asking too many questions too fast — please wait a minute and try again.", "rows": [], "sql": ""}), 429
        over = _chat_daily.consume(ip or "unknown")
        if over:
            return jsonify({"answer": _DAILY_LIMIT_MESSAGES[over], "rows": [], "sql": ""}), 429
    payload = request.get_json(silent=True) or {}
    result = answer_question(payload.get("question", ""), payload.get("history", []))
    status = result.pop("status", 200)
    return jsonify(result), status

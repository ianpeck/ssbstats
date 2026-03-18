import hmac
import os
from functools import wraps

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from ssbstats_app.repositories.seasons import get_all_seasons
from ssbstats_app.services.content import get_fighter_blurb
from ssbstats_app.services.scheduling import (
    create_scheduled_match_from_form,
    delete_scheduled_match_from_form,
    get_schedule_admin_payload,
    update_scheduled_match_from_form,
)
from ssbstats_app.services.stats import build_index_payload, get_event_detail_payload, get_fight_detail_payload, get_fights_page_filters
from ssbstats_app.utils import fighter_to_filename


pages_bp = Blueprint("pages", __name__)


def _get_request_ip():
    """Return the best client IP available for admin allowlist checks."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or ""


def _admin_ip_allowed():
    """Return whether the current request IP is allowed by env configuration."""
    request_ip = _get_request_ip()
    if request_ip in {"127.0.0.1", "::1", "localhost"}:
        return True
    raw = (os.getenv("ADMIN_ALLOWED_IPS") or "").strip()
    if not raw:
        return True
    allowed = {ip.strip() for ip in raw.split(",") if ip.strip()}
    return request_ip in allowed


def admin_required(view):
    """Protect admin pages behind login and optional IP allowlisting."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _admin_ip_allowed():
            abort(403)
        if not session.get("is_admin"):
            return redirect(url_for("pages.admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@pages_bp.route("/")
def index():
    """Render the fighter roster landing page."""
    return render_template("index.html", fighters=build_index_payload())


@pages_bp.route("/head2head")
def head2head():
    """Render the fighter comparison page shell."""
    return render_template("head2head.html")


@pages_bp.route("/fighter/<name>")
def fighter_profile(name):
    """Render a fighter profile page for the requested fighter."""
    return render_template("fighter.html", fighter_name=name, filename=fighter_to_filename(name), blurb=get_fighter_blurb(name))


@pages_bp.route("/leaderboard")
def leaderboard():
    """Render the power rankings page shell."""
    return render_template("leaderboard.html")


@pages_bp.route("/seasons")
def seasons():
    """Render the seasons page with available season options."""
    return render_template("seasons.html", seasons=get_all_seasons())


@pages_bp.route("/championships")
def championships():
    """Render the championships history page shell."""
    return render_template("championships.html")


@pages_bp.route("/events")
def events():
    """Render the PPV and event history page shell."""
    return render_template("events.html")


@pages_bp.route("/events/<slug>")
def event_detail(slug):
    """Render the dedicated event detail page."""
    payload = get_event_detail_payload(slug)
    if payload is None:
        abort(404)
    return render_template("event_detail.html", event=payload)


@pages_bp.route("/about")
def about():
    """Render the project background and architecture page."""
    return render_template("about.html")


@pages_bp.route("/fights")
def fights():
    """Render the fight log explorer with filter options."""
    return render_template("fightlog.html", **get_fights_page_filters())


@pages_bp.route("/fight/<int:fight_id>")
def fight_detail_page(fight_id):
    """Render the dedicated fight detail page."""
    payload = get_fight_detail_payload(fight_id)
    if payload is None:
        abort(404)
    return render_template("fight_detail.html", fight=payload)


@pages_bp.route("/chat")
def chat_page():
    """Render the dedicated AI stats chat page."""
    return render_template("chat.html")


@pages_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Render and process the admin login form."""
    error = ""
    if not _admin_ip_allowed():
        abort(403)
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        expected_username = os.getenv("ADMIN_USERNAME", "")
        expected_password = os.getenv("ADMIN_PASSWORD", "")
        if (
            expected_username
            and expected_password
            and hmac.compare_digest(username, expected_username)
            and hmac.compare_digest(password, expected_password)
        ):
            session["is_admin"] = True
            session["admin_username"] = username
            return redirect(request.args.get("next") or url_for("pages.admin_schedule"))
        error = "Invalid admin credentials."
    return render_template("admin_login.html", error=error)


@pages_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    """Clear the admin session."""
    session.pop("is_admin", None)
    session.pop("admin_username", None)
    return redirect(url_for("pages.index"))


@pages_bp.route("/schedule-admin", methods=["GET", "POST"])
@pages_bp.route("/admin/schedule", methods=["GET", "POST"])
@admin_required
def admin_schedule():
    """Render and submit the local-only scheduling admin page."""
    if request.method == "POST":
        action = request.form.get("form_action", "create")
        if action == "delete":
            delete_scheduled_match_from_form(request.form)
            return redirect(url_for("pages.admin_schedule", deleted=1))
        if action == "update":
            update_scheduled_match_from_form(request.form)
            return redirect(url_for("pages.admin_schedule", updated=1))
        create_scheduled_match_from_form(request.form)
        return redirect(url_for("pages.admin_schedule", saved=1))
    payload = get_schedule_admin_payload()
    return render_template(
        "admin_schedule.html",
        saved=request.args.get("saved") == "1",
        updated=request.args.get("updated") == "1",
        deleted=request.args.get("deleted") == "1",
        **payload,
    )

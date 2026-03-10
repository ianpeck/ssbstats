from flask import Blueprint, abort, render_template

from ssbstats_app.repositories.seasons import get_all_seasons
from ssbstats_app.services.content import get_fighter_blurb
from ssbstats_app.services.stats import build_index_payload, get_fight_detail_payload, get_fights_page_filters
from ssbstats_app.utils import fighter_to_filename


pages_bp = Blueprint("pages", __name__)


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

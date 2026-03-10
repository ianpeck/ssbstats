# SSB Stats

**Live site:** [ssbstats.app](https://ssbstats.app)

SSB Stats is a Flask analytics site for a long-running Super Smash Bros league that is tracked like a WWE-style franchise. It turns manually recorded match history into searchable fighter profiles, rivalry comparisons, power rankings, season summaries, championship history, event history, fight logs, and an AI-assisted stats search.

## What The Site Does

- Browse the full fighter roster with current champion badges
- Compare any two fighters across career and season-level metrics
- View fighter profile pages with accolades, streaks, charts, and fight history
- Explore all-time and season-specific power rankings
- Review season summaries, championship history, and PPV/event history
- Filter and scan detailed fight logs
- Ask natural-language questions against the stats database

## Stack

- Flask + Jinja2 for server-rendered pages and JSON APIs
- MySQL on AWS RDS for normalized league data and pre-aggregated views
- Vanilla JavaScript + Chart.js for frontend interactions and charts
- Gunicorn on AWS Elastic Beanstalk, with Cloudflare in front of the app

## Backend Layout

The backend has been split into a small Flask entrypoint plus modular route and service files:

```text
ssbstats/
├── app.py
├── ssbstats_app/
│   ├── __init__.py
│   ├── utils.py
│   ├── repositories/
│   │   ├── base.py
│   │   ├── comparisons.py
│   │   ├── elo.py
│   │   ├── events.py
│   │   ├── fighters.py
│   │   ├── fights.py
│   │   ├── leaderboards.py
│   │   ├── lookups.py
│   │   ├── power.py
│   │   └── seasons.py
│   ├── routes/
│   │   ├── api.py
│   │   └── pages.py
│   └── services/
│       ├── chat.py
│       ├── content.py
│       └── stats.py
├── templates/
│   └── partials/
├── static/
│   └── js/pages/
├── tests/
├── scripts/
│   └── maintenance/
├── generated/
├── fighters.yaml
├── DEV_GUIDE.md
└── requirements.txt
```

Responsibilities:

- `app.py`: WSGI entrypoint for local runs and Gunicorn
- `ssbstats_app/__init__.py`: app factory and blueprint registration
- `ssbstats_app/repositories/`: database access split by feature area
- `ssbstats_app/routes/`: HTTP route definitions
- `ssbstats_app/services/`: payload shaping and feature logic
- `ssbstats_app/utils.py`: shared serialization and naming helpers
- `templates/partials/`: reusable template sections for large pages like fighter profiles and comparisons
- `static/js/pages/`: page-specific frontend scripts extracted from templates
- `scripts/maintenance/`: standalone local maintenance utilities like Elo and Power Score scripts
- `generated/`: generated local artifacts produced by maintenance scripts
- `tests/`: lightweight `unittest` coverage for stable helpers and guard logic

## Local Setup

### Prerequisites

- Python 3.11 recommended
- MySQL credentials for the AWS RDS instance
- IP allowlisting for direct DB access if required by your environment

### Install

```bash
git clone <repo-url>
cd ssbstats
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp secrets.env.example secrets.env
```

Fill in `secrets.env`:

```env
awsendpoint=your-rds-endpoint.region.rds.amazonaws.com
awsuser=your_database_username
awspassword=your_database_password
awsdb=SmashBros
GROQ_API_KEY=optional_for_chat
```

### Run

```bash
python app.py
```

Open `http://localhost:5000`.

### Run Tests

```bash
python -m unittest discover tests
```

## Main Routes

### Pages

- `/` roster
- `/head2head` fighter comparison
- `/fighter/<name>` fighter profile
- `/leaderboard` power rankings
- `/seasons` season summaries
- `/championships` championship history
- `/events` PPV/event history
- `/fights` fight log explorer
- `/chat` AI stats search
- `/about` project background and architecture story

### APIs

- `/api/autocomplete/<category>`
- `/api/head2head`
- `/api/fighter/<name>`
- `/api/fighter/<name>/advanced`
- `/api/leaderboard`
- `/api/seasons`
- `/api/season/<season_id>`
- `/api/fights`
- `/api/compare`
- `/api/championships`
- `/api/events`
- `/api/chat`

## Project Strengths

- Original domain and dataset rather than reused public sample data
- Real relational modeling with derived views and computed metrics
- End-user product surface on top of the analytics layer
- Clear personal story behind the data and why it exists

## Current Gaps

- The app still depends on private database access for full local use
- There is not yet a formal automated test suite
- several templates and some frontend scripts are still larger than ideal
- The AI chat is useful, but less reliable than the deterministic stats pages

## Deployment

Production runs through Elastic Beanstalk with:

- `Procfile` -> `gunicorn --bind 0.0.0.0:8000 --workers 2 app:app`
- Cloudflare for DNS and HTTPS
- RDS MySQL for the league data

For a fuller architecture walkthrough, see [DEV_GUIDE.md](DEV_GUIDE.md).

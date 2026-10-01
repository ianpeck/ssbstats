# SSB Stats Developer Guide

This guide explains what the application does, how the backend is organized, and where to make changes without dropping everything into one file.

## Product Summary

SSB Stats is an analytics web app for a custom Super Smash Bros league that is tracked like a WWE-style promotion. The source data includes fighters, fights, seasons, PPVs, championships, brands, streaks, awards, and Elo history. The app exposes that data through server-rendered pages and JSON APIs.

## Runtime Architecture

```text
Browser
  -> Cloudflare
  -> Elastic Beanstalk / Gunicorn
  -> Flask app
  -> AWS RDS MySQL
```

The frontend is mostly server-rendered HTML plus fetch-based page enhancements. Heavy data pages load a shell first, then request JSON from `/api/...` endpoints.

## Code Layout

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
└── fighters.yaml
```

## File Responsibilities

`app.py`

- Minimal entrypoint for local development and Gunicorn
- Exposes `app` for `app:app`

`ssbstats_app/__init__.py`

- Creates the Flask app
- Registers blueprints
- Injects the static asset cache-busting version

`ssbstats_app/routes/pages.py`

- HTML page routes only
- Keeps route handlers thin
- Passes template data from service functions

`ssbstats_app/routes/api.py`

- JSON endpoints only
- Parses request args and request bodies
- Delegates payload creation to services

`ssbstats_app/repositories/`

- Database access split by feature area instead of one giant query module
- `base.py` owns low-level query helpers and connection setup
- Other repository files own feature-specific SQL

`ssbstats_app/services/content.py`

- Fighter blurbs from `fighters.yaml`
- Autocomplete caching and lookup lists

`ssbstats_app/services/stats.py`

- Feature logic for roster data, fighter payloads, rankings, seasons, fight logs, comparisons, championships, and events
- Combines multiple query calls and normalizes payloads for the frontend

`ssbstats_app/services/chat.py` and `chat_metadata.py`

- Tool-calling agent: the model gets one `run_sql` tool and loops (query, read result, fix query, answer), up to 6 steps
- `chat_metadata.py` holds the schema prompt: value encodings (`Decision` is `w`/`l`/`nc`, `DefendingIndicator` is `'y'`), gotchas and example queries. When the model gets a question wrong, the fix is usually a line here
- Model SQL runs through `run_readonly_query()` in `repositories/base.py`: read-only transaction, 5s `MAX_EXECUTION_TIME`, and the dedicated `awschatuser` login when configured
- Uses Gemini (`GEMINI_API_KEY`) or Groq (`GROQ_API_KEY`); override models with `CHAT_GEMINI_MODEL` / `CHAT_GROQ_MODEL`

`ssbstats_app/cache.py`

- `ttl_cache` keeps fighter payloads and power scores in memory (per gunicorn worker), serving stale entries instantly while refreshing in the background
- `app.py` starts a background thread that builds every fighter at startup, then runs a cheap `CHECKSUM TABLE` query each minute and rebuilds only when fights, Elo or awards change. Profiles load instantly and catch up within about a minute of new data, with no steady load on the small `db.t4g.micro` (which bills extra CPU credits if it runs hot)
- `repositories/base.py` caps concurrent queries per process (`DB_MAX_CONCURRENT_QUERIES`, default 16) because RDS allows only 60 connections in total
- Payloads built while any query failed are not cached, so a DB hiccup can't pin a half-empty profile

`ssbstats_app/security.py`

- Client IP from Cloudflare's `CF-Connecting-IP`, admin IP allowlist, per-IP rate limiting, safe login redirects
- Chat limits: 5 questions/minute per visitor, plus `DailyQuota` caps of 40/day per visitor and 100/day site-wide (shared between workers via a locked file in the temp dir; resets at midnight Eastern; admin IPs exempt)

`ssbstats_app/utils.py`

- JSON-safe serialization
- Asset filename conversion
- Championship display-name normalization

`templates/partials/`

- Reusable template sections for large pages
- Keeps page shells like `fighter.html` and `head2head.html` small and readable

`tests/`

- Small `unittest` suite for pure helpers and guard logic
- Safe place to add coverage without requiring a heavier test harness first

`scripts/maintenance/`

- Standalone local utilities that are not part of the web app runtime
- Good home for one-off or periodic DB maintenance scripts like Elo and Power Score generation

`generated/`

- Local output artifacts produced by maintenance scripts
- Should stay out of the app root and out of git

## Request Flow

Example: `GET /fighter/Mario`

1. `pages.py` renders `fighter.html`
2. The template boots and requests `/api/fighter/Mario`
3. `api.py` calls `get_fighter_profile_payload("Mario")`
4. `stats.py` runs multiple DB lookups in parallel
5. The API returns a normalized JSON payload
6. Frontend JavaScript renders charts, badges, and tables

Example: `POST /api/compare`

1. The compare page submits two fighter names
2. `api.py` validates input
3. `stats.py` combines comparison stats, power scores, fight history, and roster max values
4. The frontend renders the comparison page from a single JSON response

## Data Layer Notes

The database is MySQL on AWS RDS and the app relies heavily on prebuilt views for performance and simpler app logic. Important groups of data include:

- `careerstats`, `CareerStatsBySeason`, `CareerStatsByLocation`, `CareerStatsByFightType`, `CareerStatsByBrand`, `CareerStatsByPPV`
- `holistic_view`, `CurrentChampions`, `ChampionshipHistory`
- `longestwinstreaks`, `longestlosingstreaks`, `allwinstreaks`, `alllosingsteaks`
- `FightLog`
- `Elo`

The current DB access pattern in the repositories is:

- open a new connection per query
- execute the query
- close the connection

That is acceptable for the current traffic profile, but if the app grows, a connection pool would be a reasonable next step.

## Frontend Notes

Templates live in `templates/`, reusable sections live in `templates/partials/`, and shared JavaScript helpers live in `static/js/app.js`.

Page-specific JavaScript now lives under `static/js/pages/`. The remaining frontend cleanup work is less about inline script extraction and more about continued partialization or design cleanup where needed.

## Local Development

1. Create and activate a virtualenv
2. Install `requirements.txt`
3. Copy `secrets.env.example` to `secrets.env`
4. Add DB credentials and optional `GROQ_API_KEY`
5. Run `python app.py`
6. Run `python -m unittest discover tests`

## Deployment

Production command:

```bash
eb deploy
```

## Recommended Next Refactors

1. Add automated tests for the service layer and high-value APIs.
2. Turn the chat regression questions into an automated eval that runs against the real database.

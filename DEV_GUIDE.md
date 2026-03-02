# SSBStats Developer Guide

A plain-English walkthrough of how this app is built, what every file does, and how to make changes.

---

## The Big Picture

```
Browser  ──►  Cloudflare (HTTPS/DNS)
                  │
                  ▼
         AWS Elastic Beanstalk
         (nginx → gunicorn → Flask)
                  │
                  ▼
           AWS RDS (MySQL)
           SmashBros database
```

The user's browser talks to Cloudflare (which handles SSL/HTTPS). Cloudflare forwards the request to AWS Elastic Beanstalk, which runs the Flask app. Flask talks to an AWS RDS MySQL database to get fighter stats. The response — an HTML page or JSON data — goes back to the browser.

---

## The Tech Stack

| Layer | What it is | Why it's here |
|---|---|---|
| **Flask** | Python web framework | Handles URL routing, renders HTML pages, serves JSON for the browser's JS calls |
| **PyMySQL** | Python MySQL driver | Lets Python talk to the MySQL database |
| **Jinja2** | HTML templating (built into Flask) | Lets you put Python variables inside HTML files using `{{ }}` |
| **Gunicorn** | Production web server | Runs Flask in production (Flask's built-in server is dev-only) |
| **Nginx** | Reverse proxy (auto-managed by EB) | Sits in front of Gunicorn on the EC2 box, handles port 80 |
| **AWS Elastic Beanstalk** | Hosting platform | Manages the EC2 instance, auto-scaling, load balancer, deploys your code |
| **AWS RDS** | Managed MySQL database | The actual database with all the fight data |
| **Cloudflare** | DNS + CDN | Points ssbstats.app at the EB URL, provides free HTTPS |
| **Chart.js** | JavaScript charting library (via CDN) | Powers the charts on the Graphs page |
| **python-dotenv** | Env variable loader | Reads `secrets.env` locally so you don't hardcode passwords |

---

## File Map

```
ssbstats/
├── app.py               ← The brain — all URL routes live here
├── db.py                ← All database queries live here
├── fighters.yaml        ← Optional blurbs/descriptions per fighter
├── requirements.txt     ← Python packages to install
├── Procfile             ← Tells EB how to start the app (gunicorn command)
├── secrets.env          ← DB credentials (NOT committed to git)
├── secrets.env.example  ← Template showing what secrets.env should look like
│
├── templates/           ← HTML files (Jinja2 templates)
│   ├── base.html        ← The shared layout — navbar, CSS links, footer
│   ├── index.html       ← Home page / fighter roster grid
│   ├── head2head.html   ← Head-to-head comparison page
│   ├── fighter.html     ← Individual fighter profile page
│   ├── leaderboard.html ← Rankings page
│   └── graphs.html      ← Charts page
│
├── static/
│   ├── css/style.css    ← All styling (dark theme, animations, layout)
│   ├── js/app.js        ← Shared JavaScript (autocomplete, H2H form logic)
│   └── assets/
│       ├── fighters/    ← Fighter portrait PNGs (e.g. mario.png)
│       └── stages/      ← Stage image PNGs (e.g. finaldestinaion.png)
│
└── .elasticbeanstalk/
    └── config.yml       ← EB CLI config (app name, region, environment name)
```

---

## How a Page Load Works

### Example: User visits `/fighter/Mario`

1. **Browser** sends `GET /fighter/Mario` to Cloudflare
2. **Cloudflare** forwards it to the EB load balancer
3. **Nginx on EC2** forwards it to Gunicorn on port 8000
4. **Gunicorn** hands it to Flask
5. **Flask** (`app.py`) matches the URL to this route:
   ```python
   @app.route('/fighter/<name>')
   def fighter_profile(name):
       blurb = get_fighter_blurb(name)
       return render_template('fighter.html', fighter_name=name, ...)
   ```
6. Flask renders `templates/fighter.html` with the fighter's name passed in
7. The HTML page is returned to the browser
8. **The browser loads the page** — but the stats tables are empty at this point
9. **JavaScript** in `fighter.html` immediately calls `GET /api/fighter/Mario`
10. Flask calls `db.get_fighter_career_stats()` and `db.get_fighter_accolades()`, which fire ~17 SQL queries **in parallel** against RDS
11. Results come back as **JSON**
12. JavaScript fills in all the tables, badges, and charts with that JSON data

This split (HTML page first, then data via AJAX) is why the page loads fast and then the stats animate in.

---

## The Two Python Files

### `app.py` — Routes & Logic

Every URL the app responds to is defined here as a function with a `@app.route()` decorator.

**Page routes** (return HTML):
| Route | Function | What it does |
|---|---|---|
| `/` | `index()` | Loads fighter list + current champions, renders roster grid |
| `/head2head` | `head2head()` | Just renders the empty H2H page (data loads via JS) |
| `/fighter/<name>` | `fighter_profile()` | Renders fighter page shell (data loads via JS) |
| `/leaderboard` | `leaderboard()` | Renders empty leaderboard (data loads via JS) |
| `/graphs` | `graphs()` | Renders charts page with fighter dropdown |

**API routes** (return JSON, called by JavaScript):
| Route | What it returns |
|---|---|
| `/api/fighter/<name>` | All stats for one fighter (career, by season, accolades, etc.) |
| `/api/head2head` (POST) | H2H stats for two fighters with filters |
| `/api/leaderboard` | All fighters sorted by win rate |
| `/api/autocomplete/<category>` | List of names for search dropdowns |

**Helper functions in app.py:**
- `fighter_to_filename(name)` — converts "Banjo & Kazooie" → `"banjoandkazooie"` so image paths work
- `normalize_champ_name(s)` — replaces "Unified Tag 1" with "Unified Tag" everywhere
- `get_autocomplete_data(category)` — loads lists from DB and caches them in memory so they're not re-queried on every keystroke
- `_serialize(val)` — converts MySQL `Decimal` types to regular floats so they can be turned into JSON

### `db.py` — Database Layer

All SQL queries live here. `app.py` calls these functions; it never writes SQL directly.

**How DB connections work:**
```python
def get_connection():
    return pymysql.connect(
        host=os.getenv('awsendpoint'),   # from secrets.env or EB env var
        database=os.getenv('awsdb'),
        user=os.getenv('awsuser'),
        password=os.getenv('awspassword'),
        port=3306,
    )
```
Every query opens a fresh connection, runs the query, then closes it. This is simple and safe for low-traffic use.

**The three query helpers:**
- `select_list(query, col)` — returns a flat list of values (used for autocomplete lists)
- `select_view_row(query)` — returns a list of tuples (raw rows)
- `select_view_dicts(query)` — returns a list of dicts `{column_name: value}` (used when you need named columns)

**Parallel queries with ThreadPoolExecutor:**

For fighter profiles and H2H, there are many queries to run. Instead of waiting for each one to finish before starting the next, they all fire simultaneously:
```python
with ThreadPoolExecutor(max_workers=9) as pool:
    results = list(pool.map(run_query, queries.items()))
```
This makes pages that need 9 queries take roughly the same time as a single query.

---

## How the Front-End Works

### Templates (`templates/`)

These are HTML files with special Jinja2 tags:
- `{{ variable }}` — inserts a Python value into the HTML
- `{% for item in list %}` — loops
- `{% if condition %}` — conditionals
- `{% extends "base.html" %}` — inherits the shared layout

`base.html` contains the navbar, `<head>` with CSS links, and footer. Every other template "extends" it and fills in `{% block content %}` with its own HTML.

### Styling (`static/css/style.css`)

One big CSS file. Key concepts used:
- **CSS custom properties** (`--color-accent: #607cff`) — change one value, updates everywhere
- **Glassmorphism cards** — `backdrop-filter: blur` with semi-transparent backgrounds
- **CSS Grid / Flexbox** — used for the fighter roster grid and stat layouts
- **`@keyframes`** — animations (stat bar fills, number count-ups)
- **`.class-name`** — apply a style; **`#id-name`** — style one specific element

### JavaScript (`static/js/app.js` + inline in each template)

Shared JS is in `app.js`. Page-specific JS is in `<script>` tags at the bottom of each template.

**How the H2H page works (example of the AJAX pattern):**
1. User fills in fighters and clicks "Check Stats"
2. JS collects the form values and does:
   ```javascript
   fetch('/api/head2head', {
       method: 'POST',
       body: JSON.stringify({ fighter1: 'Mario', fighter2: 'Luigi', ... })
   })
   .then(r => r.json())
   .then(data => { /* fill in the tables */ })
   ```
3. Flask runs the queries and returns JSON
4. JS uses that JSON to build the table rows dynamically

**Autocomplete:** As you type in a fighter name box, JS calls `/api/autocomplete/fighters?q=ma` and shows a dropdown of matches. The results are cached in memory on the server so DB isn't hit on every keystroke.

---

## The Database (RDS MySQL)

The database is named `SmashBros`. Key objects the app queries:

**Views** (pre-built queries saved in MySQL — read-only, no input needed):
| View | What it contains |
|---|---|
| `careerstats` | Total W/L/% for every fighter |
| `CareerStatsBySeason` | W/L/% per fighter per season |
| `CareerStatsByLocation` | W/L/% per fighter per stage |
| `CareerStatsByFightType` | W/L/% per fighter per match type |
| `CareerStatsByBrand` | W/L/% per fighter per brand |
| `CareerStatsByPPV` | W/L/% per fighter per PPV event |
| `champfightstats` | Overall record in championship matches |
| `champfightstatsbychampionship` | Record broken out per title |
| `defendingtitle` | Record when defending a championship |
| `holistic_view` | Season-by-season summary (tournaments, rumbles, accolades) |
| `CurrentChampions` | Who currently holds each title |
| `longestwinstreaks` | Each fighter's longest win streak ever |
| `longestlosingstreaks` | Each fighter's longest loss streak ever |
| `allwinstreaks` | All win streaks; filter `Active_Win_Streak = 'Active'` for current |
| `alllosingsteaks` | All loss streaks (note: typo in DB — missing 'r') |

**Tables** (raw data):
| Table | What it contains |
|---|---|
| `ChampionshipHistory` | Every title reign (fighter, title, months held, when won) |
| `AwardHistory` + `Award` | Season awards (joined together in queries) |
| `Fighter`, `Location`, `FightType`, `PPV`, `Championship`, `Brand` | Lookup lists used for autocomplete dropdowns |

**Stored Procedures** (pre-built H2H queries):
- `headtohead(f1, f2)` — overall record vs each other
- `headtoheadLocation(f1, f2, location)` — H2H at a specific stage
- `headtoheadFightType(f1, f2, type)` — H2H for a match type
- `headtoheadSeason(f1, f2, season)` — H2H in a season
- `headtoheadMonth(f1, f2, month)` — H2H in a month
- `headtoheadChamp(f1, f2)` — H2H in championship matches
- `headtoheadPPV(f1, f2, ppv)` — H2H at a PPV event

---

## Deployment

### Infrastructure
- **EC2 instance**: `t2.micro` (1 vCPU, 1GB RAM) — free tier eligible
- **Load balancer**: Auto-created by EB, handles traffic distribution
- **S3 bucket**: Auto-created by EB to store app version zips
- **Security groups**: Firewall rules — EB instance (`sg-0f447c2a0680e3daf`) is allowed into the RDS default group on port 3306

### How to deploy a code change
```bash
# From C:\github\ssbstats, with .venv active:
eb deploy
```
This zips your code (respecting `.ebignore`), uploads to S3, and deploys to the EC2 instance. Takes ~60 seconds.

### Environment variables (secrets)
Credentials are NOT in the code. Locally, they're read from `secrets.env`. On EB, they're set as environment variables:
```bash
eb setenv awsendpoint=... awsuser=... awspassword=... awsdb=...
```
To view what's currently set: go to EB Console → ssbstats-env → Configuration → Software → Environment properties.

### eb CLI reference
```bash
eb deploy              # deploy current code
eb logs                # download recent logs
eb status              # check environment health
eb setenv KEY=value    # set/update an environment variable
eb open                # open the app URL in browser
```
The EB CLI lives at: `C:\Users\lemur\.pyenv\pyenv-win\versions\3.13.1\Scripts\eb.exe`

---

## Adding or Changing Things

### Add a fighter blurb/description
Edit `fighters.yaml` — no code change needed:
```yaml
Mario: "The OG. Consistent performer across all seasons."
Diddy Kong: "5x Brawl Champion. Elite aerial game."
```

### Add a new stat to a fighter profile
1. Add the SQL query to the `queries` dict in `db.get_fighter_accolades()` or `get_fighter_career_stats()`
2. In `app.py`'s `api_fighter()`, add the new key to the `result` dict
3. In `templates/fighter.html`, add JS to read that key and display it

### Change a color or style
Edit `static/css/style.css`. The main color variables are at the top:
```css
--color-bg: #0a0a1a;
--color-surface: #12122a;
--color-accent: #607cff;
```

### Add a new page
1. Create `templates/newpage.html` that starts with `{% extends "base.html" %}`
2. Add a route in `app.py`: `@app.route('/newpage')`
3. Add a nav link in `templates/base.html`

---

## Local Development

```bash
cd C:\github\ssbstats
.venv\Scripts\activate        # activate virtual environment
python app.py                  # starts dev server at http://localhost:5000
```

`secrets.env` must exist with real DB credentials. The dev server auto-reloads when you save a file.

The `.venv` folder contains all installed Python packages. If you need to recreate it:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

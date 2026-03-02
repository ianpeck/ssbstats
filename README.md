# SSB Stats

**Live site: [ssbstats.app](https://ssbstats.app)**

A Flask web app for viewing Super Smash Bros head-to-head statistics from an AWS RDS MySQL database. Built as a web-based successor to the [smashbrosgui](https://github.com/ianpeck22/smashbrosgui) PyQt5 desktop app.

## Features

- **Fighter Roster** — Browse all 78 fighters with portraits
- **Head to Head** — Compare any two fighters across 15 stat categories with optional filters (stage, match type, season, PPV, championship, brand, and more)
- **Leaderboard** — Power rankings sorted by win rate with sortable columns
- **Graphs** — Interactive Chart.js charts (career pie, season trends, location bars, match type, brand breakdown)
- **Fighter Profiles** — Individual career stat pages for every fighter
- Animated stat reveals, win-rate comparison bar, winner glow effect, live autocomplete search, dark glassmorphism theme

## Project Structure

```
ssbstats/
├── app.py                  # Flask app and routes
├── db.py                   # Database layer (parallel queries via ThreadPoolExecutor)
├── fighters.yaml           # Fighter bios and metadata
├── requirements.txt        # Python dependencies
├── Procfile                # Gunicorn start command for Elastic Beanstalk
├── secrets.env             # DB credentials (not committed)
├── secrets.env.example     # Credential template
├── DEV_GUIDE.md            # Developer documentation
├── static/
│   ├── css/style.css       # Dark glassmorphism theme
│   ├── js/app.js           # Autocomplete, AJAX, animations
│   └── assets/
│       ├── fighters/       # Fighter portrait PNGs
│       └── stages/         # Stage image PNGs
└── templates/
    ├── base.html
    ├── index.html          # Roster page
    ├── head2head.html      # Head-to-head comparison
    ├── fighter.html        # Fighter profile
    ├── leaderboard.html    # Power rankings
    └── graphs.html         # Charts
```

## Local Setup

### Prerequisites

- Python 3.7+
- Database access credentials (contact ianpeck22@gmail.com with your IP to be allowlisted)

### 1. Clone the repo

```bash
git clone <repo-url>
cd ssbstats
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows:**
```bash
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Add database credentials

Copy the example file and fill in your credentials:

```bash
cp secrets.env.example secrets.env
```

Edit `secrets.env`:

```
awsendpoint=your-rds-endpoint.region.rds.amazonaws.com
awsuser=your_database_username
awspassword=your_database_password
awsdb=SmashBros
```

### 6. Run the app

```bash
python app.py
```

Visit **http://localhost:5000** in your browser.

## Pages

| URL | Page |
|-----|------|
| `/` | Fighter Roster |
| `/head2head` | Head to Head Comparison |
| `/leaderboard` | Power Rankings |
| `/graphs` | Interactive Charts |
| `/fighter/<name>` | Fighter Profile (e.g. `/fighter/Mario`) |

## Deployment

The app is deployed on AWS Elastic Beanstalk (Python 3.11, t2.micro) with Cloudflare handling DNS and HTTPS. See [DEV_GUIDE.md](DEV_GUIDE.md) for a full architecture breakdown and deployment instructions.

## Database Access

This app connects to an AWS RDS MySQL instance. The code is publicly available but requires database credentials to run locally. Reach out to ianpeck22@gmail.com to request access.

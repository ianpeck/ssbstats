# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Is

A Flask web app for viewing Super Smash Bros fight statistics. Live at [ssbstats.app](https://ssbstats.app). Successor to a PyQt5 desktop app. Connects to an AWS RDS MySQL database named `SmashBros`.

## Running Locally

```bash
cd /Users/ianpeck/github/ssbstats
source .venv/bin/activate
python app.py
# visit http://localhost:5000
```

Credentials are loaded from `secrets.env` (not committed). The venv was set up with `uv`.

## Querying the Database Directly

Use the full path to the mysql client (not in default PATH):

```bash
/opt/homebrew/opt/mysql-client/bin/mysql \
  -h $(grep awsendpoint secrets.env | cut -d= -f2) \
  -u $(grep awsuser secrets.env | cut -d= -f2) \
  -p$(grep awspassword secrets.env | cut -d= -f2) \
  $(grep awsdb secrets.env | cut -d= -f2) \
  -e "YOUR QUERY HERE;"
```

## Deployment

Deployed on AWS Elastic Beanstalk. Git and deployment are independent — committing does not deploy.

```bash
eb deploy    # deploy current files to live (takes ~60 sec)
eb logs      # pull logs from EC2 to diagnose 500 errors
eb status    # check environment health
```

Secrets on EB are set via `eb setenv` (not `secrets.env`).

## Architecture

- **`app.py`** — all Flask routes. Page routes render HTML shells; data loads via AJAX from `/api/*` routes. No SQL here.
- **`db.py`** — all SQL. Every function opens a fresh PyMySQL connection, queries, and closes. Parallel queries use `ThreadPoolExecutor`.
- **`fighters.yaml`** — fighter blurbs/bios loaded per-request (no restart needed to update).
- **`templates/base.html`** — shared navbar/layout. All other templates extend it.
- **`static/css/style.css`** — dark glassmorphism theme. CSS custom properties defined at top.
- **`static/js/app.js`** — shared JS (autocomplete). Page-specific JS is inline at bottom of each template.

Autocomplete lists (fighters, locations, etc.) are cached in `_autocomplete_cache` at startup — if the DB is unreachable on startup, restart the server after fixing connectivity.

## Database — Full Reference

### Base Tables

| Table | Key Columns |
|-------|------------|
| `Fighter` | `Fighter_Name (PK)`, `Game_Series`, `Brand_ID` |
| `Fight` | `Fight_ID (PK)`, `Location_ID`, `Brand_ID`, `PPV_ID`, `Championship_ID`, `FightType_ID`, `Season_ID`, `Month`, `Week`, `Contender_Indicator` |
| `Results` | `Result_ID (PK)`, `Fighter_Name`, `Fight_ID`, `Decision (W/L)`, `Match_Result`, `Seed`, `DefendingIndicator` |
| `Championship` | `Championship_ID (PK)`, `Championship_Name` |
| `Season` | `Season_ID (PK)`, `Game` |
| `PPV` | `PPV_ID (PK)`, `PPV_Name`, `Description` |
| `Brand` | `Brand_ID (PK)`, `Brand_Name`, `Owner` |
| `Location` | `Location_ID (PK)`, `Location_Name`, `Location_GameSeries`, `Location_Origin` |
| `FightType` | `FightType_ID (PK)`, `Description` |
| `Award` | `Award_ID (PK)`, `Award_Name` |
| `AwardHistory` | `AwardHistory_ID (PK)`, `Season_ID`, `Fighter_Name`, `Award_ID` |

### Lookup Data (static)

- **Seasons**: 1–5 = Brawl era, 6–7 = Ultimate era
- **Brands**: 1=Brawl (Ethan), 2=Melee (Ian), 3=Ultimate (Shared)
- **Championships**: Melee, Animal, Special, Brawl, Human, Hardcore, Ultimate, Monster, Chaos, Smash Bros., Unified Tag 1, Unified Tag 2 — "Unified Tag 1/2" displayed as "Unified Tag" via `normalize_champ_name()`
- **FightTypes**: 3 stock, 3 minute, Coin, Special, 5 stock, 5 minute, Pokeball, Royal Rumble, Money in the Bank, 1 stock, Scramble, Tag Team, Handicap, Cash In, Tournament, 1 minute, Stamina, Smash Series

### Views

All career stat views share the pattern: `Fighter_Name, [dimension], Wins, Losses, Win Percentage`

| View | Dimension | Notes |
|------|-----------|-------|
| `careerstats` | — | Overall career totals |
| `CareerStatsBySeason` | `Season (int)` | |
| `CareerStatsByLocation` | `Location_Name` | |
| `CareerStatsByFightType` | `FightType` | |
| `CareerStatsByBrand` | `Brand` | |
| `CareerStatsByPPV` | `PPV` | |
| `CareerStatsByOpponent` | `Opponent` | H2H record vs every opponent |
| `CareerRunningStats` | per-fight | `Fighter_Name, Season, Month, Week, Fight_ID, Decision, Season_Running_Wins, Season_Running_Losses, Career_Running_Wins, Career_Running_Losses, Season_Running_Win_Pct (str), Career_Running_Win_Pct (str)` — cumulative running W/L totals and win % after each individual fight in chronological order. Used for momentum/trend charts. |

**Championship views:**
- `CurrentChampions`: `Fighter_Name, Championship_Name, Season_Won, Month_Won`
- `ChampionshipHistory`: `Fighter_Name, Championship_Name, months_held, Season_Won, Month_Won, Season_Lost, Month_Lost`
- `ChampionshipHistoryBySeason`: `Fighter_Name, Championship_Name, Season, Month_Won, Months_Held_In_Season`
- `champfightstats`: `Fighter_Name, Wins, Losses, Win Percentage` — record in all championship matches
- `champfightstatsbychampionship`: `Fighter_Name, Championship_Name, Wins, Losses, Win Percentage`
- `defendingtitle`: `Fighter_Name, Wins, Losses, Win Percentage` — record when defending a title

**Streak views:**
- `allwinstreaks`: `Win_Streak, Fighter_Name, Active_Win_Streak ('Active'/''), Season_Started, Month_Started, Week_Started, Season_Ended, Month_Ended, Week_Ended`
- `alllosingsteaks` (typo, missing 'r'): same structure with `Losing_Streak, Active_Losing_Streak`
- `longestwinstreaks`: `longest_streak, Fighter_Name` — one row per fighter, their personal best streak
- `longestlosingstreaks`: same for losses

**Fight history:**
- `FightLog`: `Fight_ID, Result_ID, Fighter_Name, Decision, Match_Result, Seed, DefendingIndicator, Location_Name, Brand_Name, PPV_Name, Championship_Name, Description (FightType), Contender_Indicator, Season, Month, Week`

**Holistic / accolades:**
- `holistic_view`: `Season, Fighter_Name, Wins, Losses, Win_Percentage, Months_With_Major, Months_With_Title, Titles_Held (text), Title_Count, Won_Tournament, Won_Royal_Rumble, Won_Scramble, Scramble_Seed_As_Winner, Won_Smash_Series, Won_Money_In_The_Bank, Won_Smash_Bros, Defended_Cash_In, Successful_Cash_In`

**Special event views:**
- `tournamentwinners`: `Season, Name, Title, Seed`
- `scramblewinner`: `Season, Name, Title, Seed`
- `cashins`: `Season_ID, Month, week, PPV_Name, Championship_Name, Fight_Winner_Name, Fight_Winner (Champion/Challenger), Fight_Loser_Name`
- `tagteamstats`: `Fighter 1, Fighter 2, Wins, Losses, Win Percentage`
- `triplecrown`: `Fighter_Name` — fighters who held the triple crown
- `ScrambleWinPercentageBySeed`: `Seed, Wins, Losses, Win Percentage`
- `TournamentWinPercentageBySeed`: `Seed, Championships, Wins, Losses, Win Percentage`

### Stored Procedures

| Procedure | Parameters | Purpose |
|-----------|-----------|---------|
| `headtohead` | `FighterOne, FighterTwo` | Overall H2H record |
| `headtoheadLocation` | `FighterOne, FighterTwo, LocationStage` | H2H at a specific stage |
| `headtoheadFightType` | `FighterOne, FighterTwo, MatchType` | H2H by match type |
| `headtoheadSeason` | `FighterOne, FighterTwo, Season` | H2H in a season |
| `headtoheadMonth` | `FighterOne, FighterTwo, Month` | H2H in a month |
| `headtoheadChamp` | `FighterOne, FighterTwo` | H2H in championship matches |
| `headtoheadPPV` | `FighterOne, FighterTwo, PPV` | H2H at a PPV |
| `headtoheadAllFighters` | `YourFighter` | Record vs every opponent |
| `allFightsBetweenTwoFighters` | `FighterOne, FighterTwo` | Every individual fight between two fighters |
| `holistic` | `My_Season` | Holistic season summary |
| `statsbyseason` | `season` | Stats for a specific season |

## Asset Naming Conventions

Fighter images live in `static/assets/fighters/` as PNGs. Names are generated by `fighter_to_filename()` in `app.py`:
- lowercase, strip spaces/periods, replace `&` with `and`
- Special case: `"Banjo & Kazooie"` → `"banjoandkazooie"`

Stage images live in `static/assets/stages/`. Names via `stage_to_filename()`: lowercase, strip spaces/commas/apostrophes/parens/hyphens.

## Rules

- **Never write to the database.** No `INSERT`, `UPDATE`, `DELETE`, `CREATE`, or `DROP` statements ever. The app and Claude are read-only consumers of the DB.
- **Fix data problems at the DB layer, not in code.** If something can be solved by adjusting a view, query, or stored procedure, do that instead of adding transformation logic in Python or JavaScript. Simpler app code is always preferred.

## Known Quirks

- `normalize_champ_name()` rewrites `"Unified Tag 1"` → `"Unified Tag"` everywhere in app output
- `_serialize()` converts MySQL `Decimal` → `float` and dates → ISO strings for JSON responses
- The `alllosingsteaks` view has a typo in the DB (missing 'r') — don't try to fix it in queries

# SSB Stats Schema Dictionary

This document is the working data dictionary for the live MySQL database behind SSB Stats. It summarizes the base tables, views, stored procedures, intended use cases, and the common join paths that matter most for analytics and chat.

## Core Grain

- `Fight` is the fight-level fact table.
- `Results` is the fighter-in-fight fact table.
- `FightLog` is the denormalized analytics view at the same grain as `Results`, with fight metadata already joined in.
- Most chat questions can be answered from:
  - pre-aggregated views for simple leaderboard/profile questions
  - `FightLog` for multi-filter and sequencing questions
  - stored procedures for direct head-to-head

## Base Tables

### `Fighter`

- Columns: `Fighter_Name`, `Game_Series`, `Brand_ID`
- Use for:
  - fighter lookup and autocomplete
  - fighter-to-brand relationship at the source-table level

### `Fight`

- Columns: `Fight_ID`, `Location_ID`, `Brand_ID`, `PPV_ID`, `Championship_ID`, `FightType_ID`, `Season_ID`, `Month`, `Week`, `Contender_Indicator`
- Use for:
  - canonical fight metadata
  - joins to dimension tables when you need normalized source data
  - season/month/week chronology

### `Results`

- Columns: `Result_ID`, `Fighter_Name`, `Fight_ID`, `Decision`, `Match_Result`, `Seed`, `DefendingIndicator`
- Use for:
  - one row per fighter per fight
  - pair with `Fight` when rebuilding fight-level context manually
  - join to `Elo` by `Result_ID`

### `Season`

- Columns: `Season_ID`, `Game`
- Use for:
  - season lookup metadata

### `Location`

- Columns: `Location_ID`, `Location_Name`, `Location_GameSeries`, `Location_Origin`
- Use for:
  - location lookup and metadata

### `FightType`

- Columns: `FightType_ID`, `Description`
- Use for:
  - fight type lookup and labels

### `PPV`

- Columns: `PPV_ID`, `PPV_Name`, `Description`
- Use for:
  - event lookup and metadata

### `Brand`

- Columns: `Brand_ID`, `Brand_Name`, `Owner`
- Use for:
  - brand lookup and ownership metadata

### `Championship`

- Columns: `Championship_ID`, `Championship_Name`, `championship_tier`
- Use for:
  - belt definitions and tiering

### `Award`

- Columns: `Award_ID`, `Award_Name`
- Use for:
  - award lookup

### `AwardHistory`

- Columns: `AwardHistory_ID`, `Season_ID`, `Fighter_Name`, `Award_ID`
- Use for:
  - award winners by season

### `Elo`

- Columns: `elo_id`, `result_id`, `fighter_name`, `fight_id`, `elo_before`, `elo_after`
- Use for:
  - Elo history
  - current/peak/average Elo
  - fight-by-fight rating movement
- Common joins:
  - `Elo.result_id = Results.Result_ID`
  - `Elo.fight_id = Fight.Fight_ID`

### `FightStage`

- Columns: `Fight_ID`, `Location_ID`, `Brand_ID`, `PPV_ID`, `Championship_ID`, `FightType_ID`, `Season_ID`, `Month`, `Week`, `Contender_Indicator`
- Use for:
  - appears to mirror fight metadata in stage-oriented workflows
  - not currently central to app runtime queries

### `ResultsStage`

- Columns: `Result_ID`, `Fighter_Name`, `Fight_ID`, `Decision`, `Match_Result`, `Seed`, `DefendingIndicator`
- Use for:
  - stage-oriented copy of result grain
  - not currently central to app runtime queries

## Denormalized Analytics View

### `FightLog`

- Columns: `Fight_ID`, `Result_ID`, `Fighter_Name`, `Decision`, `Match_Result`, `Seed`, `DefendingIndicator`, `Location_Name`, `Brand_Name`, `PPV_Name`, `Championship_Name`, `Description`, `Contender_Indicator`, `Season`, `Month`, `Week`
- Grain:
  - one row per fighter per fight
- Use for:
  - chat questions with combined filters
  - fight log page
  - pre-fight and post-fight sequencing
  - season / PPV / championship / location / fight-type slicing
- Important rule:
  - use `COUNT(DISTINCT Fight_ID)` when counting fights from `FightLog`

## Career Aggregate Views

### `careerstats`

- Columns: `Fighter_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - all-time wins/losses/fights/record leaderboards
  - quick single-fighter career summary

### `CareerStatsBySeason`

- Columns: `Fighter_Name`, `Season`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - season-scoped fighter rankings
  - a fighter’s record in one season

### `CareerStatsByLocation`

- Columns: `Fighter_Name`, `Location_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - best/worst fighters at a stage
  - one fighter’s stage record

### `CareerStatsByFightType`

- Columns: `Fighter_Name`, `FightType`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - fight-type performance

### `CareerStatsByBrand`

- Columns: `Fighter_Name`, `Brand`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - brand-specific records

### `CareerStatsByPPV`

- Columns: `Fighter_Name`, `PPV`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - all-time PPV performance by fighter
- Caveat:
  - no `Season` column, so season-scoped PPV questions must use `FightLog`

### `CareerStatsByOpponent`

- Columns: `Fighter_Name`, `Opponent`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - rank all opponents against one fighter
  - single-fighter opponent splits

### `CareerRunningStats`

- Columns: `Fighter_Name`, `Season`, `Month`, `Week`, `Fight_ID`, `Decision`, `Season_Running_Wins`, `Season_Running_Losses`, `Career_Running_Wins`, `Career_Running_Losses`, `Season_Running_Win_Pct`, `Career_Running_Win_Pct`
- Use for:
  - momentum/trend charts
  - “at that point in time” snapshots
  - pre/post-fight running record

## Championship Views

### `CurrentChampions`

- Columns: `Fighter_Name`, `Championship_Name`, `Season_Won`, `Month_Won`
- Use for:
  - current title holders

### `ChampionshipHistory`

- Columns: `Fighter_Name`, `Championship_Name`, `Championship_Tier`, `months_held`, `Season_Won`, `Month_Won`, `Season_Lost`, `Month_Lost`
- Use for:
  - title lineage
  - total reigns
  - longest reigns
  - title history by fighter

### `ChampionshipHistoryBySeason`

- Columns: `Fighter_Name`, `Championship_Name`, `Championship_Tier`, `Season`, `Month_Won`, `Months_Held_In_Season`
- Use for:
  - season-specific championship timeline questions

### `champfightstats`

- Columns: `Fighter_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - overall championship-match record by fighter

### `champfightstatsbychampionship`

- Columns: `Fighter_Name`, `Championship_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - record in matches for one specific championship

### `defendingtitle`

- Columns: `Fighter_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - title-defense record

### `cashins`

- Columns: `Season_ID`, `Month`, `week`, `PPV_Name`, `Championship_Name`, `Fight_Winner_Name`, `Fight_Winner`, `Fight_Loser_Name`
- Use for:
  - cash-in history

## Streak Views

### `allwinstreaks`

- Columns: `Win_Streak`, `Fighter_Name`, `Active_Win_Streak`, `Season_Started`, `Month_Started`, `Week_Started`, `Season_Ended`, `Month_Ended`, `Week_Ended`
- Use for:
  - all historical win streak runs
  - longest streak in a given season
  - active streak lookup

### `alllosingsteaks`

- Columns: `Losing_Streak`, `Fighter_Name`, `Active_Losing_Streak`, `Season_Started`, `Month_Started`, `Week_Started`, `Season_Ended`, `Month_Ended`, `Week_Ended`
- Use for:
  - all historical losing streak runs
  - active losing streak lookup

### `longestwinstreaks`

- Columns: `longest_streak`, `Fighter_Name`
- Use for:
  - all-time personal-best win streaks

### `longestlosingstreaks`

- Columns: `longest_streak`, `Fighter_Name`
- Use for:
  - all-time personal-worst losing streaks

## Season/Achievement Views

### `holistic_view`

- Columns: `Season`, `Fighter_Name`, `Wins`, `Losses`, `Win_Percentage`, `Months_With_Major`, `Months_With_Title`, `Titles_Held`, `Title_Count`, `Won_Tournament`, `Won_Royal_Rumble`, `Won_Scramble`, `Scramble_Seed_As_Winner`, `Won_Smash_Series`, `Won_Money_In_The_Bank`, `Won_Smash_Bros`, `Defended_Cash_In`, `Successful_Cash_In`
- Use for:
  - season recaps
  - event winners
  - title months / major months
  - feature-rich season ranking enrichment

### `majorwinner`

- Columns: `Fighter_Name`, `melee_wins`, `brawl_wins`, `ultimate_wins`
- Use for:
  - major-title holder summaries

### `triplecrown`

- Columns: `Fighter_Name`
- Use for:
  - fighters who completed the triple crown

### `tagteamstats`

- Columns: `Fighter 1`, `Fighter 2`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - team-pair records

### `stagechecks`

- Columns: `Fighter_Name`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - stage-check or special validation workflows

### `scramblewinner`

- Columns: `Season`, `Name`, `Title`, `Seed`
- Use for:
  - scramble winners by season

### `tournamentwinners`

- Columns: `Season`, `Name`, `Title`, `Seed`
- Use for:
  - tournament winners by season

### `ScrambleWinPercentageBySeed`

- Columns: `Seed`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - scramble performance by seed

### `TournamentWinPercentageBySeed`

- Columns: `Seed`, `Championships`, `Wins`, `Losses`, `Win Percentage`
- Use for:
  - tournament performance by seed

## Stored Procedures

### Head-to-head family

- `headtohead(FighterOne, FighterTwo)`
- `headtoheadSeason(FighterOne, FighterTwo, Season)`
- `headtoheadMonth(FighterOne, FighterTwo, Month)`
- `headtoheadLocation(FighterOne, FighterTwo, LocationStage)`
- `headtoheadFightType(FighterOne, FighterTwo, MatchType)`
- `headtoheadChamp(FighterOne, FighterTwo)`
- `headtoheadPPV(FighterOne, FighterTwo, PPV)`
- `headtoheadAllFighters(YourFighter)`
- `allFightsBetweenTwoFighters(FighterOne, FighterTwo)`

Use these for:
- direct matchup questions
- matchup slicing by season, location, fight type, championship match, or PPV

### Other procedures

- `holistic`
- `statsbyseason`

Use these for:
- season and holistic summary workflows where procedure output is preferable to ad hoc aggregation

## Common Join Paths

### Canonical fight reconstruction

```sql
Results.Fight_ID = Fight.Fight_ID
```

Use this when you need normalized fight metadata from the base tables.

### Fighter results with Elo

```sql
Results.Result_ID = Elo.result_id
Results.Fight_ID = Elo.fight_id
```

Use this for:
- Elo movement by fighter
- opponent strength / strength-of-schedule calculations

### Fight metadata to dimensions

```sql
Fight.Location_ID = Location.Location_ID
Fight.Brand_ID = Brand.Brand_ID
Fight.PPV_ID = PPV.PPV_ID
Fight.Championship_ID = Championship.Championship_ID
Fight.FightType_ID = FightType.FightType_ID
Fight.Season_ID = Season.Season_ID
```

Use this when the denormalized `FightLog` view is not enough.

### Awards

```sql
AwardHistory.Award_ID = Award.Award_ID
AwardHistory.Fighter_Name = Fighter.Fighter_Name
AwardHistory.Season_ID = Season.Season_ID
```

Use this for:
- award winners by season
- award history by fighter

## Chat Guidance

For chat and ad hoc analytics:

- use `careerstats` for simple all-time wins/losses/fights/record
- use `CareerStatsBy*` views for one-dimensional splits
- use `FightLog` for combined filters or event chronology
- use `CareerRunningStats` and streak views for pre/post-fight and temporal questions
- use `ChampionshipHistory` / `CurrentChampions` for title lineage
- use head-to-head procedures for direct fighter-vs-fighter questions
- use `Elo` joined to `Fight` or `Results` for rating history and advanced ranking features

## Source Selection Rules

- If the question asks about title wins, title reigns, capturing a belt, holding a championship, or how many times someone won a specific title:
  - use `ChampionshipHistory`
  - optionally use `CurrentChampions` if the question is about present-day holders
- If the question asks about championship-match record:
  - use `champfightstats` or `champfightstatsbychampionship`
- If the question asks about title defenses or record while defending:
  - first distinguish count from record
  - for `most title defenses` or `number of successful defenses`, count winning `FightLog` rows filtered on `DefendingIndicator`
  - for `defending record` or `win percentage while defending`, use `defendingtitle`
- If the question asks about current holders:
  - use `CurrentChampions`
- If the question asks about longest reign, months held, or lineage:
  - use `ChampionshipHistory`
- If the question asks about major titles or major championships:
  - filter on `Championship.championship_tier = 'Major'`
  - or use `ChampionshipHistory.Championship_Tier = 'Major'` if the question is about reigns/lineage
- If the question asks about season-specific PPV performance:
  - use `FightLog`
  - do not use `CareerStatsByPPV` because it is not season-scoped
- If the question asks about all-time PPV record:
  - use `CareerStatsByPPV`
- If the question asks about one fighter versus every opponent:
  - use `CareerStatsByOpponent`
- If the question asks about direct matchup between exactly two fighters:
  - use the `headtohead*` stored procedures when possible
- If the question asks about pre-fight or post-fight chronology:
  - use `FightLog`, `CareerRunningStats`, `allwinstreaks`, or `alllosingsteaks`
- If the question asks about Elo movement or rating state:
  - use `Elo`
  - join to `Fight` or `Results` only when chronology or metadata is needed

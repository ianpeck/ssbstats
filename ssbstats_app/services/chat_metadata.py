"""Central metadata registry for chat planning, schema knowledge, and metric semantics."""

from textwrap import dedent


QUERY_TYPES = [
    "rank_fighters",
    "fighter_stat",
    "rank_opponents",
    "head_to_head",
    "current_champions",
    "title_history",
    "bounce_back_after_loss",
    "generic_sql",
]


METRICS = [
    "wins",
    "losses",
    "fights",
    "win_pct",
    "longest_win_streak",
    "title_reigns",
]


RANKINGS = [
    "top",
    "bottom",
]


SCOPES = [
    "all_time",
    "season",
]


CONTEXT_TYPES = [
    "location",
    "ppv",
    "fight_type",
    "brand",
    "championship",
    "championship_matches",
]


VIEW_DEFINITIONS = [
    ("careerstats", "Fighter_Name, Wins, Losses, `Win Percentage`", "overall fighter summary"),
    ("CareerStatsBySeason", "Fighter_Name, Season, Wins, Losses, `Win Percentage`", "fighter summary by season"),
    ("CareerStatsByLocation", "Fighter_Name, Location_Name, Wins, Losses, `Win Percentage`", "fighter summary by location"),
    ("CareerStatsByFightType", "Fighter_Name, FightType, Wins, Losses, `Win Percentage`", "fighter summary by fight type"),
    ("CareerStatsByBrand", "Fighter_Name, Brand, Wins, Losses, `Win Percentage`", "fighter summary by brand"),
    ("CareerStatsByPPV", "Fighter_Name, PPV, Wins, Losses, `Win Percentage`", "fighter summary by PPV"),
    ("CareerStatsByOpponent", "Fighter_Name, Opponent, Wins, Losses, `Win Percentage`", "fighter summary by opponent"),
    ("CareerRunningStats", "Fighter_Name, Season, Month, Week, Fight_ID, Season_Running_Wins, Season_Running_Losses, Career_Running_Wins, Career_Running_Losses, Season_Running_Win_Pct, Career_Running_Win_Pct", "pre/post-fight running totals"),
    ("CurrentChampions", "Fighter_Name, Championship_Name, Season_Won, Month_Won", "current title holders"),
    ("ChampionshipHistory", "Fighter_Name, Championship_Name, Championship_Tier, months_held, Season_Won, Month_Won, Season_Lost, Month_Lost", "title reign history"),
    ("champfightstats", "Fighter_Name, Wins, Losses, `Win Percentage`", "overall championship-match record"),
    ("champfightstatsbychampionship", "Fighter_Name, Championship_Name, Wins, Losses, `Win Percentage`", "record by specific championship"),
    ("defendingtitle", "Fighter_Name, Wins, Losses, `Win Percentage`", "record while defending a title"),
    ("longestwinstreaks", "Fighter_Name, longest_streak", "best win streak per fighter"),
    ("longestlosingstreaks", "Fighter_Name, longest_streak", "worst losing streak per fighter"),
    ("allwinstreaks", "Fighter_Name, Win_Streak, Active_Win_Streak, Season_Started, Month_Started, Week_Started, Season_Ended, Month_Ended, Week_Ended", "all win streak runs"),
    ("alllosingsteaks", "Fighter_Name, Losing_Streak, Active_Losing_Streak, Season_Started, Month_Started, Week_Started, Season_Ended, Month_Ended, Week_Ended", "all losing streak runs"),
    ("holistic_view", "Fighter_Name, Season, Months_With_Title, Months_With_Major, Won_Tournament, Won_Royal_Rumble, Won_Scramble, Won_Smash_Series, Won_Money_In_The_Bank, Won_Smash_Bros, Successful_Cash_In", "season-level accolade summary"),
    ("Elo", "result_id, fight_id, fighter_name, elo_before, elo_after", "per-result Elo history"),
]


BASE_TABLES = [
    ("FightLog", "Fight_ID, Result_ID, Fighter_Name, Decision, Match_Result, Seed, DefendingIndicator, Location_Name, Brand_Name, PPV_Name, Championship_Name, Description, Contender_Indicator, Season, Month, Week", "core event grain: one row per fighter per fight"),
    ("Fighter", "Fighter_Name", "fighter lookup"),
    ("Location", "Location_Name", "location lookup"),
    ("FightType", "Description", "fight type lookup"),
    ("PPV", "PPV_Name", "PPV lookup"),
    ("Championship", "Championship_Name", "championship lookup"),
    ("Brand", "Brand_Name", "brand lookup"),
]


STORED_PROCEDURES = [
    ("SmashBros.headtohead(%s, %s)", "overall head-to-head between two fighters"),
    ("SmashBros.headtoheadSeason(%s, %s, %s)", "head-to-head between two fighters in one season"),
    ("SmashBros.headtoheadLocation(%s, %s, %s)", "head-to-head between two fighters at one location"),
    ("SmashBros.headtoheadPPV(%s, %s, %s)", "head-to-head between two fighters at one PPV"),
    ("SmashBros.headtoheadFightType(%s, %s, %s)", "head-to-head between two fighters in one fight type"),
    ("SmashBros.headtoheadChamp(%s, %s)", "head-to-head between two fighters in championship matches"),
]


JOIN_RULES = [
    "FightLog is the base fact table. One fighter in one fight is one row.",
    "Use COUNT(DISTINCT Fight_ID) when counting fights from FightLog.",
    "FightLog joins to Elo on FightLog.Result_ID = Elo.result_id.",
    "FightLog entity columns are already denormalized for most filters: Fighter_Name, Location_Name, Brand_Name, PPV_Name, Championship_Name, Description, Season, Month, Week.",
    "Prefer pre-aggregated views when they already answer the question cleanly.",
    "Use FightLog directly when the question needs combined conditions, per-fight sequencing, or pre-fight state reconstruction.",
]


METRIC_DEFINITIONS = [
    "wins = total wins for a fighter in the chosen scope/context.",
    "losses = total losses for a fighter in the chosen scope/context.",
    "fights = wins + losses for a fighter in the chosen scope/context.",
    "win_pct = win percentage in the chosen scope/context; use minimum_sample when the user implies meaningfulness.",
    "head-to-head = direct meetings between exactly the named fighters.",
    "championship matches = FightLog rows where Championship_Name is not null/blank.",
    "bounce back after a loss = result in the immediate next fight after a prior loss, ordered by Season, Month, Week, Fight_ID.",
    "title_reigns = count of reigns in ChampionshipHistory for a fighter.",
]


PLANNER_RULES = [
    "Map the question into a semantic stats plan, not a canned intent label.",
    "Use rank_fighters for leaderboard questions like most wins, most losses, most fights, best record, worst record, longest win streak.",
    "Use fighter_stat for questions about one fighter's wins, losses, fights, record, or streak.",
    "Use rank_opponents when the user asks who is best/worst against one named fighter.",
    "Use head_to_head for direct matchup questions between two fighters, optionally with season/context filters.",
    "Use current_champions for current champion / who holds which title questions.",
    "Use title_history for questions about what titles a fighter has held or how many title reigns they have.",
    "Use bounce_back_after_loss for questions about the fight immediately after a loss.",
    "If the question asks for best record in a context, use metric win_pct with ranking top.",
    "If the question asks for worst record in a context, use metric win_pct with ranking bottom.",
    "If the question asks for most losses, use metric losses with ranking top.",
    "If the question asks for fewest losses, use metric losses with ranking bottom.",
    "If the question asks for most fights/matches, use metric fights with ranking top.",
    "If the question asks for most wins, use metric wins with ranking top.",
    "If the question asks for longest win streak, use metric longest_win_streak with ranking top.",
    "If a question clearly names a season, set scope to season and fill season.",
    "If a fighter-specific or head-to-head question is missing the fighter names, set needs_clarification true.",
]


def render_planner_prompt():
    """Build the planner prompt from shared metadata."""
    query_types = "\n".join(f"- {value}" for value in QUERY_TYPES)
    metrics = "\n".join(f"- {value}" for value in METRICS)
    rankings = "\n".join(f"- {value}" for value in RANKINGS)
    scopes = "\n".join(f"- {value}" for value in SCOPES)
    context_types = "\n".join(f"- {value}" for value in CONTEXT_TYPES)
    rules = "\n".join(f"- {rule}" for rule in PLANNER_RULES)
    metric_defs = "\n".join(f"- {item}" for item in METRIC_DEFINITIONS)
    return dedent(
        f"""
        You are planning how to answer a stats question for a Super Smash Bros league site.

        Convert the user's question into a semantic stats plan.
        Do not write SQL.

        Supported query_type values:
        {query_types}

        Supported metric values:
        {metrics}

        Supported ranking values:
        {rankings}

        Supported scope values:
        {scopes}

        Supported context_type values:
        {context_types}

        Metric definitions:
        {metric_defs}

        Planner rules:
        {rules}

        Return ONLY JSON with this shape:
        {{
          "query_type": "one_of_the_types_above",
          "metric": "",
          "ranking": "",
          "scope": "all_time",
          "fighter_names": ["optional", "fighter", "names"],
          "season": 0,
          "minimum_sample": 0,
          "context_type": "",
          "context_value": "",
          "needs_clarification": false,
          "clarification_question": ""
        }}
        """
    ).strip()


def render_legacy_schema_prompt():
    """Build the fallback SQL prompt from shared schema metadata."""
    views = "\n".join(
        f"- {name}: {columns} ({description})"
        for name, columns, description in VIEW_DEFINITIONS
    )
    tables = "\n".join(
        f"- {name}: {columns} ({description})"
        for name, columns, description in BASE_TABLES
    )
    sprocs = "\n".join(f"- {name}: {description}" for name, description in STORED_PROCEDURES)
    joins = "\n".join(f"- {rule}" for rule in JOIN_RULES)
    metrics = "\n".join(f"- {item}" for item in METRIC_DEFINITIONS)
    return dedent(
        f"""
        You are a sports statistics assistant for SSB Stats — a WWE-style franchise using Super Smash Bros characters.
        Answer questions ONLY using data from the MySQL database described below. Do not make up data.

        VIEW LAYER
        ==========
        {views}

        BASE TABLES
        ===========
        {tables}

        STORED PROCEDURES
        =================
        {sprocs}

        JOIN / GRAIN RULES
        ==================
        {joins}

        METRIC DEFINITIONS
        ==================
        {metrics}

        SQL RULES
        =========
        - Return only SELECT or WITH queries.
        - COUNT(DISTINCT Fight_ID) when counting fights from FightLog.
        - Prefer views when they already contain the answer.
        - Use FightLog when the question needs combined filters, sequencing, or per-fight reconstruction.

        Return ONLY a JSON object:
        {{
          "sql": "your query",
          "explanation": "one sentence"
        }}
        """
    ).strip()

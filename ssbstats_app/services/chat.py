import json
import os
import re

from flask import current_app

from ssbstats_app.repositories.base import select_view_dicts
from ssbstats_app.utils import serialize_value

try:
    from groq import Groq as GroqClient
except ImportError:
    GroqClient = None


_GROQ_CLIENT = None


def get_groq_client():
    """Lazily initialize and return the Groq client, if configured."""
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None and GroqClient and os.getenv("GROQ_API_KEY"):
        _GROQ_CLIENT = GroqClient(api_key=os.getenv("GROQ_API_KEY"))
    return _GROQ_CLIENT


def guard_sql(sql):
    """Reject unsafe or overly complex LLM-generated SQL."""
    original_sql = sql.strip()
    sql_lower = original_sql.lower()
    if not re.match(r"^\s*(select|with)\b", sql_lower):
        return None, "Only SELECT queries are allowed."
    if ";" in original_sql[:-1]:
        return None, "Multiple SQL statements are not allowed."
    if len(original_sql) > 1200:
        return None, "Query too large."
    for banned in ["cross join", "information_schema", "sleep(", "benchmark(", "into outfile", "load_file", "union select"]:
        if banned in sql_lower:
            return None, "Disallowed SQL pattern detected."
    if sql_lower.count("select") > 4:
        return None, "Query too complex."
    if " limit " not in sql_lower:
        return original_sql.rstrip(";") + " LIMIT 100", None
    return original_sql, None


def answer_question(question, history):
    """Run the chat pipeline: generate SQL, execute it, and summarize results."""
    client = get_groq_client()
    if not client:
        return {"error": "Chat is not configured (missing GROQ_API_KEY).", "status": 503}

    question = str(question or "").strip()[:500]
    history = (history or [])[-3:]
    if not question:
        return {"error": "No question provided.", "status": 400}

    try:
        messages = [{"role": "system", "content": _CHAT_SCHEMA}]
        for item in history:
            prior_question = str(item.get("question", ""))[:300]
            prior_sql = str(item.get("sql", ""))
            prior_rows = item.get("rows", [])
            messages.append({"role": "user", "content": prior_question})
            messages.append({"role": "assistant", "content": json.dumps({"sql": prior_sql, "explanation": f"Query returned {len(prior_rows)} rows: {json.dumps(prior_rows[:5])}"})})
        messages.append({"role": "user", "content": question})

        sql_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0,
            max_tokens=512,
        )
        raw = sql_resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return {"answer": "Sorry, I couldn't understand that question. Try rephrasing it.", "status": 200}

        sql = parsed.get("sql", "").strip()
        sql, guard_error = guard_sql(sql)
        if guard_error:
            return {"answer": "I can only answer read-only questions about the stats database.", "status": 200}

        try:
            rows = select_view_dicts(sql)
        except Exception as db_err:
            current_app.logger.warning("[chat] initial SQL error: %s | SQL: %s", db_err, sql)
            fix_resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": _CHAT_SCHEMA},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That query failed with error: {db_err}. Please correct the SQL and return the same JSON format."},
                ],
                temperature=0,
                max_tokens=512,
            )
            raw2 = fix_resp.choices[0].message.content.strip()
            if raw2.startswith("```"):
                raw2 = re.sub(r"^```[a-z]*\n?", "", raw2).rstrip("`").strip()
            try:
                parsed2 = json.loads(raw2)
            except Exception as parse_err:
                current_app.logger.warning("[chat] self-correction JSON parse error: %s | raw: %s", parse_err, raw2)
                return {"answer": "I couldn't understand that question — try rephrasing it.", "status": 200}
            sql = parsed2.get("sql", "").strip()
            sql, guard_error = guard_sql(sql)
            if guard_error:
                return {"answer": "I couldn't find an answer to that question.", "status": 200}
            try:
                rows = select_view_dicts(sql)
            except Exception as db_err2:
                current_app.logger.warning("[chat] corrected SQL also failed: %s | SQL: %s", db_err2, sql)
                return {"answer": "I had trouble with that query — could you rephrase the question?", "sql": sql, "error": str(db_err2), "status": 200}

        serialized = [{key: serialize_value(value) for key, value in row.items()} for row in rows[:50]]
        has_rows = bool(serialized)
        answer_messages = [{
            "role": "system",
            "content": (
                "You are a friendly, conversational sports stats assistant for a Super Smash Bros wrestling franchise. "
                "Do not mention SQL or databases. Keep responses casual and natural, not robotic.\n\n"
                + (
                    "IMPORTANT: The query returned data rows. You MUST give a direct, confident answer using those rows. "
                    "Do not hedge, do not say you are stumped, do not ask to rephrase. The data is correct — just answer the question in 1-3 sentences."
                    if has_rows
                    else "The query returned no results. Use your judgment:\n"
                    "- If the query was specific and targeted (named fighters, specific event, etc.), respond with CONVICTION that it never happened. "
                    'Examples: "Nope, those two have never faced each other in a championship.", "That matchup has never taken place."\n'
                    '- If the query was vague and may have missed something, suggest rephrasing. Examples: "Hmm, I\'m not sure I caught that — could you rephrase?", "That one\'s tricky, try wording it differently."'
                )
            ),
        }]
        for item in history:
            answer_messages.append({"role": "user", "content": item.get("question", "")})
            answer_messages.append({"role": "assistant", "content": f"I found {len(item.get('rows', []))} results for that."})
        answer_messages.append({"role": "user", "content": f"Question: {question}\n\nQuery used: {sql}\n\nResult rows ({len(serialized)} rows): {json.dumps(serialized)}"})

        answer_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=answer_messages,
            temperature=0.3,
            max_tokens=300,
        )
        return {"answer": answer_resp.choices[0].message.content.strip(), "rows": serialized, "sql": sql, "status": 200}
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "rate_limit_exceeded" in err_str or "tokens per day" in err_str:
            return {"answer": "We've hit the daily AI token limit — the chat will be back up within a few hours. Check back soon!", "status": 200}
        return {"error": f"Something went wrong: {exc}", "status": 500}


_CHAT_SCHEMA = """
You are a sports statistics assistant for SSB Stats — a WWE-style franchise using Super Smash Bros characters.
Answer questions ONLY using data from the MySQL database described below. Do not make up data.

QUESTION INTERPRETATION:
When the user asks for your "opinion", "favorite", "pick", or "prediction" (e.g. "who is the best in your opinion?", "who do you think is the GOAT?"), DO NOT refuse. Treat these as data questions and answer using the database stats. Rephrase internally as "who does the data say is the best?" and query accordingly. Never say you cannot have an opinion — instead, say something like "Based on the stats, here's what the data says..." and then provide the query results.

DATABASE SCHEMA
===============

VIEWS (pre-built, use these first):
IMPORTANT: The win percentage column is named "Win Percentage" (with a space — NOT Win_Percentage). Always quote it with backticks: `Win Percentage`
- careerstats: Fighter_Name, Wins, Losses, `Win Percentage`
- CareerStatsBySeason: Fighter_Name, Season, Wins, Losses, `Win Percentage`
- CareerStatsByLocation: Fighter_Name, Location_Name, Wins, Losses, `Win Percentage`
- CareerStatsByFightType: Fighter_Name, FightType, Wins, Losses, `Win Percentage`
- CareerStatsByBrand: Fighter_Name, Brand, Wins, Losses, `Win Percentage`
- CareerStatsByPPV: Fighter_Name, PPV, Wins, Losses, `Win Percentage`
- CareerStatsByOpponent: Fighter_Name, Opponent, Wins, Losses
- CareerRunningStats: Fighter_Name, Season, Month, Week, Fight_ID, Season_Running_Wins, Season_Running_Losses, Career_Running_Wins, Career_Running_Losses, Season_Running_Win_Pct, Career_Running_Win_Pct
- ChampionshipHistory: Fighter_Name, Championship_Name, Championship_Tier, months_held, Season_Won, Month_Won, Season_Lost, Month_Lost
  * Season_Lost = NULL means currently active champion
  * Championship_Tier values: 'Major', 'Minor', 'Specialty', 'Tag'
- CurrentChampions: Fighter_Name, Championship_Name, Season_Won, Month_Won
- champfightstats: Fighter_Name, Wins, Losses, `Win Percentage` (stats in championship matches only)
- champfightstatsbychampionship: Fighter_Name, Championship_Name, Wins, Losses, `Win Percentage`
- defendingtitle: Fighter_Name, Wins, Losses, `Win Percentage` (stats when defending a title)
- allwinstreaks: Fighter_Name, Win_Streak, Active_Win_Streak, Season_Started, Month_Started, Week_Started, Season_Ended, Month_Ended, Week_Ended
- alllosingsteaks: Fighter_Name, Losing_Streak, Active_Losing_Streak, Season_Started, Month_Started, Week_Started, Season_Ended, Month_Ended, Week_Ended
- longestwinstreaks: Fighter_Name, longest_streak
- longestlosingstreaks: Fighter_Name, longest_streak
- FightLog: Fight_ID, Result_ID, Fighter_Name, Decision (W/L), Match_Result, Seed, DefendingIndicator, Location_Name, Brand_Name, PPV_Name, Championship_Name, Description (fight type), Contender_Indicator, Season, Month, Week
- holistic_view: Fighter_Name, Season, Months_With_Title, Months_With_Major, Won_Tournament, Won_Royal_Rumble, Won_Scramble, Won_Smash_Series, Won_Money_In_The_Bank, Won_Smash_Bros, Successful_Cash_In
- Elo: result_id, fight_id, fighter_name, elo_before (float), elo_after (float)
- triplecrown: Fighter_Name
- majorwinner: Fighter_Name (+ columns for each major title won)

BASE TABLES (for lookups):
- Fighter: Fighter_Name
- Location: Location_Name
- FightType: Description
- PPV: PPV_Name
- Championship: Championship_Name
- Brand: Brand_Name
- Award: Award_ID, Award_Name
- AwardHistory: Season_ID, Fighter_Name, Award_ID

POWER SCORE (computed metric — NOT stored in the database):
Power Score is a 0–100 composite ranking computed by the website, not stored in the DB.

KEY RULES:
- Only generate SELECT queries. Never generate INSERT, UPDATE, DELETE, DROP, or any DDL.
- A fight can have multiple rows in FightLog (one per participant). To count distinct fights, always use COUNT(DISTINCT Fight_ID).
- Prefer views over raw FightLog queries when a view already aggregates the needed data.
- When a question asks about a specific fighter, use WHERE Fighter_Name = 'ExactName'.

RESPONSE FORMAT:
Return ONLY a JSON object with exactly these keys:
{
  "sql": "your SELECT query here",
  "explanation": "one sentence describing what the query does"
}
Do not include any other text, markdown, or formatting outside the JSON object.
""".strip()

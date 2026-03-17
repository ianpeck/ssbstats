import json
import os
import re

from flask import current_app

from ssbstats_app.repositories.base import h2h_query_sql, select_view_dicts
from ssbstats_app.services.chat_metadata import render_agent_prompt, render_legacy_schema_prompt, render_planner_prompt
from ssbstats_app.services.chat_state import apply_chat_state, build_chat_state, extract_fighter_names
from ssbstats_app.services.content import get_autocomplete_data
from ssbstats_app.utils import normalize_champ_name, serialize_value

try:
    from openai import OpenAI as OpenAIClient
except ImportError:
    OpenAIClient = None

try:
    from groq import Groq as GroqClient
except ImportError:
    GroqClient = None


_GEMINI_CLIENT = None
_GROQ_CLIENT = None
_GEMINI_MODEL = "gemini-2.5-flash"
_PLANNER_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_MIN_SAMPLE = 5
_AGENT_PROMPT = render_agent_prompt()
_PLANNER_PROMPT = render_planner_prompt()
_LEGACY_CHAT_SCHEMA = render_legacy_schema_prompt()
_DANGEROUS_REQUEST_PATTERNS = [
    r"\bdelete\b",
    r"\bdrop\b",
    r"\btruncate\b",
    r"\balter\b",
    r"\binsert\b",
    r"\bupdate\b",
    r"\bremove\b",
    r"\berase\b",
    r"\bwipe\b",
]


def get_gemini_client():
    """Lazily initialize and return the Gemini client via OpenAI-compatible endpoint."""
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None and OpenAIClient and os.getenv("GEMINI_API_KEY"):
        _GEMINI_CLIENT = OpenAIClient(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return _GEMINI_CLIENT


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
    if not re.match(r"^\s*(select|with|call)\b", sql_lower):
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
    original_sql = original_sql.rstrip(";")
    if re.match(r"^\s*call\b", sql_lower):
        return original_sql, None
    if not re.search(r"\blimit\b", sql_lower):
        return original_sql + " LIMIT 100", None
    return original_sql, None


def guard_question(question):
    """Reject destructive natural-language requests before any model call."""
    lower = str(question or "").lower()
    for pattern in _DANGEROUS_REQUEST_PATTERNS:
        if re.search(pattern, lower):
            return (
                "I can't help with deleting, dropping, updating, or otherwise modifying database data. "
                "I can only answer read-only questions about the stats."
            )
    return None


def answer_question(question, history):
    """Answer a stats question using a semantic plan plus deterministic executors."""
    question = str(question or "").strip()[:500]
    if not question:
        return {"error": "No question provided.", "status": 400}

    blocked_reason = guard_question(question)
    if blocked_reason:
        return {"answer": blocked_reason, "rows": [], "sql": "", "status": 200}

    gemini = get_gemini_client()
    client = gemini or get_groq_client()
    if not client:
        return {"error": "Chat is not configured (missing GEMINI_API_KEY or GROQ_API_KEY).", "status": 503}

    model = _GEMINI_MODEL if gemini else _PLANNER_MODEL

    try:
        result = _schema_grounded_answer_question(client, model, question, history or [])
        if result:
            return result
        return _legacy_sql_answer_question(client, model, question, history)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "rate_limit_exceeded" in err_str or "tokens per day" in err_str:
            return {"answer": "We've hit the daily AI token limit — the chat will be back up within a few hours. Check back soon!", "status": 200}
        return {"error": f"Something went wrong: {exc}", "status": 500}


def _plan_question(client, model, question, state):
    """Use the LLM to convert a natural-language question into a semantic stats plan."""
    raw_plan = {}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _PLANNER_PROMPT},
                {"role": "system", "content": f"Recent conversation state: {json.dumps(state)}"},
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_tokens=2048,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        raw_plan = json.loads(raw)
    except Exception:
        raw_plan = {}
    return _normalize_plan(raw_plan, question, state)


def _schema_grounded_answer_question(client, model, question, history):
    """Run the SQL-first schema-grounded agent before any semantic fallback."""
    history = (history or [])[-3:]
    state = build_chat_state(history)
    messages = [
        {"role": "system", "content": _AGENT_PROMPT},
        {"role": "system", "content": f"Recent conversation state: {json.dumps(state)}"},
    ]
    for item in history:
        prior_question = str(item.get("question", ""))[:300]
        prior_sql = str(item.get("sql", ""))
        prior_rows = item.get("rows", [])
        messages.append({"role": "user", "content": prior_question})
        messages.append({"role": "assistant", "content": json.dumps({"sql": prior_sql, "result_preview": prior_rows[:5]})})
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=2048,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)
    except Exception:
        return None

    if parsed.get("needs_clarification"):
        return {
            "answer": parsed.get("clarification_question") or "I need a little more detail to answer that correctly.",
            "rows": [],
            "sql": "",
            "status": 200,
        }

    sql = str(parsed.get("sql", "")).strip()
    if not sql:
        return None

    sql, guard_error = guard_sql(sql)
    if guard_error:
        current_app.logger.warning("[chat] schema agent guard error: %s | SQL: %s", guard_error, sql)
        return None

    try:
        if sql.strip().lower().startswith("call"):
            rows = h2h_query_sql(sql)
        else:
            rows = select_view_dicts(sql)
    except Exception as db_err:
        current_app.logger.warning("[chat] schema agent SQL error: %s | SQL: %s", db_err, sql)
        repaired = _repair_schema_sql(client, model, question, history, sql, str(db_err), state)
        if not repaired:
            return None
        sql = repaired
        try:
            if sql.strip().lower().startswith("call"):
                rows = h2h_query_sql(sql)
            else:
                rows = select_view_dicts(sql)
        except Exception as db_err2:
            current_app.logger.warning("[chat] repaired schema agent SQL error: %s | SQL: %s", db_err2, sql)
            return None

    serialized = _serialize_rows(rows)
    answer = _compose_schema_grounded_answer(client, model, question, sql, serialized)
    return {"answer": answer, "rows": serialized, "sql": sql, "status": 200}


def _repair_schema_sql(client, model, question, history, sql, error_text, state):
    """Ask the model to repair a failed read-only SQL query using the schema prompt."""
    messages = [
        {"role": "system", "content": _AGENT_PROMPT},
        {"role": "system", "content": f"Recent conversation state: {json.dumps(state)}"},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Broken SQL: {sql}\n\n"
                f"Database error: {error_text}\n\n"
                "Return corrected JSON in the same format."
            ),
        },
    ]
    for item in history[-2:]:
        prior_question = str(item.get("question", ""))[:300]
        prior_sql = str(item.get("sql", ""))
        messages.append({"role": "user", "content": prior_question})
        messages.append({"role": "assistant", "content": json.dumps({"sql": prior_sql, "result_preview": (item.get("rows", [])[:5])})})
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=2048,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)
        repaired_sql = str(parsed.get("sql", "")).strip()
    except Exception:
        return None
    repaired_sql, guard_error = guard_sql(repaired_sql)
    if guard_error:
        return None
    return repaired_sql


def _compose_schema_grounded_answer(client, model, question, sql, rows):
    """Use the model to phrase a query result without mentioning SQL."""
    answer_messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly, concise sports stats analyst for a Super Smash Bros league. "
                "Answer using the returned data only. Do not mention SQL or databases. "
                "If there are no rows, say so plainly."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nQuery used: {sql}\n\nResult rows ({len(rows)} rows): {json.dumps(rows[:20])}",
        },
    ]
    try:
        answer_resp = client.chat.completions.create(
            model=model,
            messages=answer_messages,
            temperature=0.1,
            max_tokens=1024,
        )
        return answer_resp.choices[0].message.content.strip()
    except Exception:
        if not rows:
            return "I couldn't find anything matching that in the stats."
        return "I found the data, but I couldn't phrase it cleanly."


def _normalize_plan(raw_plan, question, state):
    """Normalize planner JSON and apply heuristic correction for obvious stat requests."""
    plan = {
        "query_type": str(raw_plan.get("query_type") or "generic_sql").strip(),
        "metric": str(raw_plan.get("metric") or "").strip(),
        "ranking": str(raw_plan.get("ranking") or "").strip().lower(),
        "scope": str(raw_plan.get("scope") or "all_time").strip().lower(),
        "fighter_names": [str(name).strip() for name in raw_plan.get("fighter_names", []) if str(name).strip()],
        "season": int(raw_plan.get("season") or 0),
        "minimum_sample": int(raw_plan.get("minimum_sample") or 0),
        "context_type": str(raw_plan.get("context_type") or "").strip().lower(),
        "context_value": str(raw_plan.get("context_value") or "").strip(),
        "needs_clarification": bool(raw_plan.get("needs_clarification")),
        "clarification_question": str(raw_plan.get("clarification_question") or "").strip(),
    }

    extracted_fighters = extract_fighter_names(question)
    if extracted_fighters:
        plan["fighter_names"] = _merge_unique_names(plan["fighter_names"], extracted_fighters)

    season_match = re.search(r"\bseason\s+(\d+)\b", question, flags=re.IGNORECASE)
    if season_match and not plan["season"]:
        plan["season"] = int(season_match.group(1))
    if plan["season"] and plan["scope"] != "season":
        plan["scope"] = "season"

    if not plan["minimum_sample"] and plan["metric"] == "win_pct":
        plan["minimum_sample"] = 1

    plan = apply_chat_state(plan, state, question)
    return _apply_plan_heuristics(plan, question)


def _apply_plan_heuristics(plan, question):
    """Correct common planner misses using lightweight semantic heuristics."""
    lower = question.lower()
    fighter_count = len(plan.get("fighter_names", []))

    if "current champion" in lower or "current champions" in lower or "who holds" in lower:
        plan["query_type"] = "current_champions"
        return plan

    if "title" in lower and fighter_count >= 1 and any(phrase in lower for phrase in ["what titles", "how many titles", "title reigns", "held"]):
        plan["query_type"] = "title_history"
        return plan

    if "after a loss" in lower or "after losing" in lower:
        plan["query_type"] = "bounce_back_after_loss"
        plan["metric"] = "win_pct"
        if not plan["minimum_sample"]:
            plan["minimum_sample"] = _DEFAULT_MIN_SAMPLE
        return plan

    if "longest win streak" in lower or "win streak" in lower and any(word in lower for word in ["longest", "best"]):
        plan["metric"] = "longest_win_streak"
        plan["ranking"] = "top"
        plan["query_type"] = "fighter_stat" if fighter_count == 1 and not any(word in lower for word in ["who has", "leader", "most"]) else "rank_fighters"
        return plan

    if fighter_count >= 2 or any(token in lower for token in [" vs ", " versus ", "head-to-head", "head to head", "faced each other"]):
        plan["query_type"] = "head_to_head"
        return plan

    if fighter_count == 1 and "against" in lower and any(word in lower for word in ["best", "worst"]):
        plan["query_type"] = "rank_opponents"
        plan["metric"] = "win_pct"
        plan["ranking"] = "bottom" if "worst" in lower else "top"
        return plan

    if fighter_count == 1 and any(phrase in lower for phrase in ["lost the most to", "lost most to", "has lost the most to"]):
        plan["query_type"] = "rank_opponents"
        plan["metric"] = "wins"
        plan["ranking"] = "top"
        return plan

    if any(phrase in lower for phrase in ["most fights", "most matches", "fought the most"]):
        plan["query_type"] = "rank_fighters" if fighter_count != 1 else "fighter_stat"
        plan["metric"] = "fights"
        plan["ranking"] = "top"
        return plan

    if any(phrase in lower for phrase in ["most losses", "loss leader", "most defeats"]):
        plan["query_type"] = "rank_fighters" if fighter_count != 1 else "fighter_stat"
        plan["metric"] = "losses"
        plan["ranking"] = "top"
        return plan

    if any(phrase in lower for phrase in ["fewest losses", "least losses"]):
        plan["query_type"] = "rank_fighters" if fighter_count != 1 else "fighter_stat"
        plan["metric"] = "losses"
        plan["ranking"] = "bottom"
        return plan

    if any(phrase in lower for phrase in ["most wins", "wins leader", "winningest"]):
        plan["query_type"] = "rank_fighters" if fighter_count != 1 else "fighter_stat"
        plan["metric"] = "wins"
        plan["ranking"] = "top"
        return plan

    if "best record" in lower:
        plan["query_type"] = "rank_opponents" if fighter_count == 1 and "against" in lower else ("fighter_stat" if fighter_count == 1 else "rank_fighters")
        plan["metric"] = "win_pct"
        plan["ranking"] = "top"
        return plan

    if "worst record" in lower:
        plan["query_type"] = "rank_opponents" if fighter_count == 1 and "against" in lower else ("fighter_stat" if fighter_count == 1 else "rank_fighters")
        plan["metric"] = "win_pct"
        plan["ranking"] = "bottom"
        return plan

    if "record" in lower and fighter_count == 1:
        plan["query_type"] = "fighter_stat"
        plan["metric"] = plan["metric"] or "win_pct"
        return plan

    return plan


def _execute_planned_query(plan, question):
    """Execute a semantic stats plan."""
    query_type = plan.get("query_type")
    if query_type == "rank_fighters":
        return _execute_rank_fighters(plan)
    if query_type == "fighter_stat":
        return _execute_fighter_stat(plan)
    if query_type == "rank_opponents":
        return _execute_rank_opponents(plan)
    if query_type == "head_to_head":
        return _execute_head_to_head(plan)
    if query_type == "current_champions":
        return _execute_current_champions()
    if query_type == "title_history":
        return _execute_title_history(plan)
    if query_type == "bounce_back_after_loss":
        return _execute_bounce_back_after_loss(plan)
    return None


def _execute_rank_fighters(plan):
    """Rank fighters by a general metric within an optional scope/context."""
    metric = plan.get("metric") or "win_pct"
    if metric == "longest_win_streak":
        if plan.get("scope") == "season" and plan.get("season"):
            season = plan["season"]
            order = "DESC" if plan.get("ranking") != "bottom" else "ASC"
            sql = (
                "SELECT Fighter_Name AS fighter_name, MAX(Win_Streak) AS longest_streak "
                "FROM allwinstreaks "
                "WHERE Season_Started <= %s AND COALESCE(Season_Ended, Season_Started) >= %s "
                f"GROUP BY Fighter_Name ORDER BY longest_streak {order}, Fighter_Name ASC LIMIT 10"
            )
            rows = select_view_dicts(sql, (season, season))
            return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (season, season))}
        order = "DESC" if plan.get("ranking") != "bottom" else "ASC"
        sql = (
            "SELECT Fighter_Name AS fighter_name, longest_streak "
            f"FROM longestwinstreaks ORDER BY longest_streak {order}, Fighter_Name ASC LIMIT 10"
        )
        return {"rows": _serialize_rows(select_view_dicts(sql)), "sql": sql}

    if plan.get("context_type"):
        return _execute_rank_from_fightlog(plan)

    if plan.get("scope") == "season" and plan.get("season"):
        return _execute_rank_from_season_view(plan)

    return _execute_rank_from_careerstats(plan)


def _execute_fighter_stat(plan):
    """Return one fighter's stat line within an optional scope/context."""
    fighters = _resolve_fighter_names(plan.get("fighter_names", []))
    if not fighters:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which fighter do you want that stat for?",
        }
    plan = dict(plan)
    plan["fighter_names"] = fighters
    metric = plan.get("metric") or "win_pct"
    fighter = fighters[0]

    if metric == "longest_win_streak":
        if plan.get("scope") == "season" and plan.get("season"):
            season = plan["season"]
            sql = (
                "SELECT Fighter_Name AS fighter_name, MAX(Win_Streak) AS longest_streak "
                "FROM allwinstreaks "
                "WHERE Fighter_Name = %s AND Season_Started <= %s AND COALESCE(Season_Ended, Season_Started) >= %s "
                "GROUP BY Fighter_Name LIMIT 1"
            )
            rows = select_view_dicts(sql, (fighter, season, season))
            return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter, season, season))}
        sql = (
            "SELECT Fighter_Name AS fighter_name, longest_streak "
            "FROM longestwinstreaks WHERE Fighter_Name = %s LIMIT 1"
        )
        rows = select_view_dicts(sql, (fighter,))
        return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter,))}

    if plan.get("context_type"):
        return _execute_fighter_stat_from_fightlog(plan)

    if plan.get("scope") == "season" and plan.get("season"):
        sql = (
            "SELECT Fighter_Name AS fighter_name, Wins AS wins, Losses AS losses, "
            "`Win Percentage` AS win_pct, (Wins + Losses) AS fights "
            "FROM CareerStatsBySeason WHERE Fighter_Name = %s AND Season = %s LIMIT 1"
        )
        rows = select_view_dicts(sql, (fighter, plan["season"]))
        return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter, plan["season"]))}

    sql = (
        "SELECT Fighter_Name AS fighter_name, Wins AS wins, Losses AS losses, "
        "`Win Percentage` AS win_pct, (Wins + Losses) AS fights "
        "FROM careerstats WHERE Fighter_Name = %s LIMIT 1"
    )
    rows = select_view_dicts(sql, (fighter,))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter,))}


def _execute_rank_opponents(plan):
    """Rank opponents against a single anchor fighter."""
    fighters = _resolve_fighter_names(plan.get("fighter_names", []))
    if not fighters:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which fighter do you want to rank opponents against?",
        }
    fighter = fighters[0]
    ranking = plan.get("ranking") or "top"
    order = "DESC" if ranking == "top" else "ASC"
    min_sample = plan.get("minimum_sample") or 1
    metric = plan.get("metric") or "win_pct"
    if metric == "wins":
        order_clause = f"Wins {order}, Losses ASC, fights DESC"
    elif metric == "losses":
        order_clause = f"Losses {order}, Wins DESC, fights DESC"
    else:
        order_clause = f"CAST(REPLACE(`Win Percentage`, '%', '') AS DECIMAL(5,2)) {order}, Wins DESC, fights DESC"
    sql = (
        "SELECT Opponent AS opponent, Wins AS wins, Losses AS losses, "
        "`Win Percentage` AS win_pct, (Wins + Losses) AS fights "
        "FROM CareerStatsByOpponent "
        "WHERE Fighter_Name = %s AND (Wins + Losses) >= %s "
        f"ORDER BY {order_clause} LIMIT 10"
    )
    rows = select_view_dicts(sql, (fighter, min_sample))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter, min_sample))}


def _execute_head_to_head(plan):
    """Execute overall or contextual head-to-head queries."""
    fighters = _resolve_fighter_names(plan.get("fighter_names", []))
    if len(fighters) < 2:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which two fighters do you want to compare head-to-head?",
        }
    f1, f2 = fighters[:2]
    context_type = plan.get("context_type")
    context_value = _resolve_context_value(context_type, plan.get("context_value", ""))
    if context_type == "location" and context_value:
        rows = h2h_query_sql("CALL SmashBros.headtoheadLocation(%s, %s, %s)", (f1, f2, context_value))
        return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtoheadLocation({_sql_quote(f1)}, {_sql_quote(f2)}, {_sql_quote(context_value)})"}
    if context_type == "ppv" and context_value:
        rows = h2h_query_sql("CALL SmashBros.headtoheadPPV(%s, %s, %s)", (f1, f2, context_value))
        return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtoheadPPV({_sql_quote(f1)}, {_sql_quote(f2)}, {_sql_quote(context_value)})"}
    if context_type == "fight_type" and context_value:
        rows = h2h_query_sql("CALL SmashBros.headtoheadFightType(%s, %s, %s)", (f1, f2, context_value))
        return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtoheadFightType({_sql_quote(f1)}, {_sql_quote(f2)}, {_sql_quote(context_value)})"}
    if context_type == "championship_matches":
        rows = h2h_query_sql("CALL SmashBros.headtoheadChamp(%s, %s)", (f1, f2))
        return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtoheadChamp({_sql_quote(f1)}, {_sql_quote(f2)})"}
    if plan.get("scope") == "season" and plan.get("season"):
        season = plan["season"]
        rows = h2h_query_sql("CALL SmashBros.headtoheadSeason(%s, %s, %s)", (f1, f2, season))
        return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtoheadSeason({_sql_quote(f1)}, {_sql_quote(f2)}, {season})"}
    rows = h2h_query_sql("CALL SmashBros.headtohead(%s, %s)", (f1, f2))
    return {"rows": _serialize_rows(rows), "sql": f"CALL SmashBros.headtohead({_sql_quote(f1)}, {_sql_quote(f2)})"}


def _execute_current_champions():
    """Return the current champion list."""
    sql = (
        "SELECT Fighter_Name AS fighter_name, Championship_Name AS championship_name, "
        "Season_Won AS season_won, Month_Won AS month_won "
        "FROM CurrentChampions ORDER BY Championship_Name"
    )
    rows = select_view_dicts(sql)
    for row in rows:
        row["championship_name"] = normalize_champ_name(row.get("championship_name"))
    return {"rows": _serialize_rows(rows), "sql": sql}


def _execute_title_history(plan):
    """Return title history for one fighter."""
    fighters = _resolve_fighter_names(plan.get("fighter_names", []))
    if not fighters:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which fighter do you want title history for?",
        }
    fighter = fighters[0]
    sql = (
        "SELECT Championship_Name AS championship_name, Season_Won AS season_won, Month_Won AS month_won, "
        "Season_Lost AS season_lost, Month_Lost AS month_lost, months_held "
        "FROM ChampionshipHistory WHERE Fighter_Name = %s ORDER BY Season_Won, Month_Won"
    )
    rows = select_view_dicts(sql, (fighter,))
    for row in rows:
        row["championship_name"] = normalize_champ_name(row.get("championship_name"))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, (fighter,))}


def _execute_bounce_back_after_loss(plan):
    """Return record in the immediate fight after a loss."""
    fighters = _resolve_fighter_names(plan.get("fighter_names", []))
    min_sample = plan.get("minimum_sample") or _DEFAULT_MIN_SAMPLE
    sql = (
        "WITH ordered AS ( "
        "SELECT Fighter_Name, Fight_ID, Decision, Season, Month, COALESCE(Week,99) AS WeekSort, "
        "LAG(Decision) OVER (PARTITION BY Fighter_Name ORDER BY Season, Month, COALESCE(Week,99), Fight_ID) AS prev_decision "
        "FROM FightLog "
        "), bounce AS ( "
        "SELECT Fighter_Name, Decision FROM ordered WHERE prev_decision IN ('l','L') "
        ") "
        "SELECT Fighter_Name AS fighter_name, "
        "SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) AS wins_after_loss, "
        "SUM(CASE WHEN Decision IN ('l','L') THEN 1 ELSE 0 END) AS losses_after_loss, "
        "ROUND(100 * SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_pct_after_loss, "
        "COUNT(*) AS opportunities FROM bounce "
    )
    if fighters:
        fighter = fighters[0]
        filtered_sql = sql + "WHERE Fighter_Name = %s GROUP BY Fighter_Name HAVING COUNT(*) >= %s LIMIT 1"
        rows = select_view_dicts(filtered_sql, (fighter, min_sample))
        return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(filtered_sql, (fighter, min_sample))}
    ranked_sql = (
        sql
        + "GROUP BY Fighter_Name HAVING COUNT(*) >= %s "
        + "ORDER BY win_pct_after_loss DESC, opportunities DESC, wins_after_loss DESC LIMIT 10"
    )
    rows = select_view_dicts(ranked_sql, (min_sample,))
    return {"rows": _serialize_rows(rows), "sql": ranked_sql.replace("%s", str(min_sample), 1)}


def _execute_rank_from_careerstats(plan):
    """Use careerstats for all-time fighter ranking metrics."""
    metric = plan.get("metric") or "win_pct"
    ranking = plan.get("ranking") or "top"
    order = "DESC" if ranking == "top" else "ASC"
    metric_expr, metric_alias = _metric_expression_for_views(metric)
    base_sql = (
        "SELECT Fighter_Name AS fighter_name, Wins AS wins, Losses AS losses, "
        "(Wins + Losses) AS fights, `Win Percentage` AS win_pct"
    )
    if metric_alias not in {"wins", "losses", "fights", "win_pct"}:
        base_sql += f", {metric_expr} AS {metric_alias}"
    sql = base_sql + " FROM careerstats"
    if metric == "win_pct":
        min_sample = plan.get("minimum_sample") or 1
        sql += " WHERE (Wins + Losses) >= %s"
        sql += f" ORDER BY {metric_expr} {order}, Wins DESC, fights DESC LIMIT 10"
        rows = select_view_dicts(sql, (min_sample,))
        return {"rows": _serialize_rows(rows), "sql": sql.replace("%s", str(min_sample), 1)}
    sql += f" ORDER BY {metric_expr} {order}, Wins DESC, fights DESC LIMIT 10"
    return {"rows": _serialize_rows(select_view_dicts(sql)), "sql": sql}


def _execute_rank_from_season_view(plan):
    """Use CareerStatsBySeason for season-scoped fighter ranking metrics."""
    metric = plan.get("metric") or "win_pct"
    ranking = plan.get("ranking") or "top"
    order = "DESC" if ranking == "top" else "ASC"
    season = plan.get("season")
    metric_expr, metric_alias = _metric_expression_for_views(metric)
    base_sql = (
        "SELECT Fighter_Name AS fighter_name, Wins AS wins, Losses AS losses, "
        "(Wins + Losses) AS fights, `Win Percentage` AS win_pct"
    )
    if metric_alias not in {"wins", "losses", "fights", "win_pct"}:
        base_sql += f", {metric_expr} AS {metric_alias}"
    sql = base_sql + " FROM CareerStatsBySeason WHERE Season = %s"
    params = [season]
    if metric == "win_pct":
        min_sample = plan.get("minimum_sample") or 1
        sql += " AND (Wins + Losses) >= %s"
        params.append(min_sample)
    sql += f" ORDER BY {metric_expr} {order}, Wins DESC, fights DESC LIMIT 10"
    rows = select_view_dicts(sql, tuple(params))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, params)}


def _execute_rank_from_fightlog(plan):
    """Aggregate FightLog for contextual ranking metrics."""
    context = _build_context_filter(plan.get("context_type"), _resolve_context_value(plan.get("context_type"), plan.get("context_value", "")))
    if not context:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which location, PPV, fight type, brand, or championship context do you want?",
        }
    ranking = plan.get("ranking") or "top"
    order = "DESC" if ranking == "top" else "ASC"
    metric = plan.get("metric") or "win_pct"
    params = list(context["params"])
    clauses = [context["where_sql"]]
    if plan.get("scope") == "season" and plan.get("season"):
        clauses.append("Season = %s")
        params.append(plan["season"])
    sql = (
        "SELECT Fighter_Name AS fighter_name, "
        "SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN Decision IN ('l','L') THEN 1 ELSE 0 END) AS losses, "
        "COUNT(*) AS fights, "
        "ROUND(100 * SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_pct "
        "FROM FightLog WHERE "
        + " AND ".join(clauses)
        + " GROUP BY Fighter_Name"
    )
    if metric == "win_pct":
        min_sample = plan.get("minimum_sample") or 1
        sql += " HAVING COUNT(*) >= %s"
        params.append(min_sample)
    metric_order = "wins" if metric == "wins" else "losses" if metric == "losses" else "fights" if metric == "fights" else "win_pct"
    sql += f" ORDER BY {metric_order} {order}, wins DESC, fights DESC LIMIT 10"
    rows = select_view_dicts(sql, tuple(params))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, params)}


def _execute_fighter_stat_from_fightlog(plan):
    """Aggregate FightLog for one fighter within a context."""
    context = _build_context_filter(plan.get("context_type"), _resolve_context_value(plan.get("context_type"), plan.get("context_value", "")))
    if not context:
        return {
            "rows": [],
            "sql": "",
            "answer_override": "Which location, PPV, fight type, brand, or championship context do you want?",
        }
    fighter = plan["fighter_names"][0]
    params = [fighter, *context["params"]]
    clauses = ["Fighter_Name = %s", context["where_sql"]]
    if plan.get("scope") == "season" and plan.get("season"):
        clauses.append("Season = %s")
        params.append(plan["season"])
    sql = (
        "SELECT Fighter_Name AS fighter_name, "
        "SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN Decision IN ('l','L') THEN 1 ELSE 0 END) AS losses, "
        "COUNT(*) AS fights, "
        "ROUND(100 * SUM(CASE WHEN Decision IN ('w','W') THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_pct "
        "FROM FightLog WHERE "
        + " AND ".join(clauses)
        + " GROUP BY Fighter_Name LIMIT 1"
    )
    rows = select_view_dicts(sql, tuple(params))
    return {"rows": _serialize_rows(rows), "sql": _render_debug_sql(sql, params)}


def _compose_answer(plan, executed, question):
    """Turn a semantic query result into a concise natural-language answer."""
    if executed.get("answer_override"):
        return executed["answer_override"]
    rows = executed.get("rows", [])
    if not rows:
        return "I couldn't find anything matching that in the stats."

    query_type = plan.get("query_type")
    top = rows[0]

    if query_type == "current_champions":
        champion_bits = [f"{row['championship_name']}: {row['fighter_name']}" for row in rows[:8]]
        return "Current champions: " + "; ".join(champion_bits) + "."

    if query_type == "title_history":
        fighter = _resolve_fighter_names(plan.get("fighter_names", []))[0]
        title_names = [row["championship_name"] for row in rows]
        return f"{fighter} has held {len(rows)} title reigns: " + ", ".join(title_names) + "."

    if query_type == "bounce_back_after_loss":
        if plan.get("fighter_names"):
            return (
                f"{top['fighter_name']} is {top['wins_after_loss']}-{top['losses_after_loss']} "
                f"in the fight immediately after a loss ({top['win_pct_after_loss']} over {_fmt_count(top['opportunities'])} chances)."
            )
        return (
            f"{top['fighter_name']} has the best record in the fight immediately after a loss at "
            f"{top['wins_after_loss']}-{top['losses_after_loss']} "
            f"({top['win_pct_after_loss']} over {_fmt_count(top['opportunities'])} chances)."
        )

    if query_type == "head_to_head":
        return _compose_head_to_head_answer(plan, rows, question)

    if query_type == "rank_opponents":
        fighter = _resolve_fighter_names(plan.get("fighter_names", []))[0]
        metric = plan.get("metric") or "win_pct"
        if metric == "wins":
            return (
                f"{top['opponent']} has lost the most to {fighter}, with {fighter} going "
                f"{_fmt_count(top['wins'])}-{_fmt_count(top['losses'])} against them."
            )
        adjective = "best" if (plan.get("ranking") or "top") == "top" else "worst"
        return (
            f"The {adjective} record against {fighter} belongs to {top['opponent']}, "
            f"who is {_fmt_count(top['wins'])}-{_fmt_count(top['losses'])} ({top['win_pct']}) against them."
        )

    if query_type == "fighter_stat":
        metric = plan.get("metric") or "win_pct"
        if metric == "longest_win_streak":
            return f"{top['fighter_name']}'s longest recorded win streak is {_fmt_count(top['longest_streak'])}{_suffix_for_plan(plan)}."
        return (
            f"{top['fighter_name']} has {_fmt_count(top['wins'])} wins and {_fmt_count(top['losses'])} losses "
            f"({_fmt_count(top['fights'])} fights, {top['win_pct']}){_suffix_for_plan(plan)}."
        )

    if query_type == "rank_fighters":
        metric = plan.get("metric") or "win_pct"
        descriptor = _describe_metric(metric, plan.get("ranking") or "top")
        if metric == "longest_win_streak":
            return f"{top['fighter_name']} has the {descriptor} at {_fmt_count(top['longest_streak'])} straight wins."
        if metric == "wins":
            return f"{top['fighter_name']} has the {descriptor} with {_fmt_count(top['wins'])} wins{_suffix_for_plan(plan)}."
        if metric == "losses":
            return f"{top['fighter_name']} has the {descriptor} with {_fmt_count(top['losses'])} losses{_suffix_for_plan(plan)}."
        if metric == "fights":
            return (
                f"{top['fighter_name']} has the {descriptor} at {_fmt_count(top['fights'])} total fights "
                f"({_fmt_count(top['wins'])}-{_fmt_count(top['losses'])}, {top['win_pct']}){_suffix_for_plan(plan)}."
            )
        return (
            f"{top['fighter_name']} has the {descriptor} at {_fmt_count(top['wins'])}-{_fmt_count(top['losses'])} "
            f"({top['win_pct']}){_suffix_for_plan(plan)}."
        )

    return "I found a result, but I couldn't phrase it cleanly yet."


def _compose_head_to_head_answer(plan, rows, question):
    """Format a direct or contextual head-to-head answer."""
    if len(rows) < 2:
        return "I couldn't find a head-to-head result for those two."
    left, right = rows[0], rows[1]
    total_fights = int(left.get("Wins", 0)) + int(left.get("Losses", 0))
    context_suffix = _suffix_for_plan(plan)
    lower = question.lower()
    if any(phrase in lower for phrase in ["how many times", "how many fights", "how many matches", "how often"]):
        if left.get("Wins") == left.get("Losses"):
            return (
                f"{left['Fighter']} and {right['Fighter']} have faced each other {total_fights} times{context_suffix}, "
                f"and the series is tied {left['Wins']}-{left['Losses']}."
            )
        leader = left["Fighter"] if int(left["Wins"]) > int(left["Losses"]) else right["Fighter"]
        return (
            f"{left['Fighter']} and {right['Fighter']} have faced each other {total_fights} times{context_suffix}. "
            f"{leader} leads the series {left['Wins']}-{left['Losses']}."
        )
    if left.get("Wins") == left.get("Losses"):
        return (
            f"{left['Fighter']} and {right['Fighter']} are tied head-to-head at {left['Wins']}-{left['Losses']} "
            f"({total_fights} fights{context_suffix})."
        )
    return (
        f"{left['Fighter']} leads the head-to-head {left['Wins']}-{left['Losses']} over {right['Fighter']} "
        f"({left['W/L %']} win rate, {total_fights} fights{context_suffix})."
    )


def _metric_expression_for_views(metric):
    """Return a sortable SQL expression for view-backed ranking."""
    if metric == "wins":
        return "Wins", "wins"
    if metric == "losses":
        return "Losses", "losses"
    if metric == "fights":
        return "(Wins + Losses)", "fights"
    return "CAST(REPLACE(`Win Percentage`, '%', '') AS DECIMAL(5,2))", "win_pct_value"


def _build_context_filter(context_type, context_value):
    """Build a FightLog WHERE fragment for a supported context."""
    if context_type == "location" and context_value:
        return {"where_sql": "Location_Name = %s", "params": [context_value]}
    if context_type == "ppv" and context_value:
        return {"where_sql": "PPV_Name = %s", "params": [context_value]}
    if context_type == "fight_type" and context_value:
        return {"where_sql": "Description = %s", "params": [context_value]}
    if context_type == "brand" and context_value:
        return {"where_sql": "Brand_Name = %s", "params": [context_value]}
    if context_type == "championship" and context_value:
        return {"where_sql": "Championship_Name = %s", "params": [context_value]}
    if context_type == "championship_matches":
        return {"where_sql": "Championship_Name IS NOT NULL AND Championship_Name != ''", "params": []}
    return None


def _resolve_fighter_names(names):
    """Resolve freeform fighter names against the canonical fighter list."""
    canonical = {name.lower(): name for name in get_autocomplete_data("fighters")}
    resolved = []
    for name in names:
        lowered = name.lower()
        if lowered in canonical:
            resolved.append(canonical[lowered])
            continue
        partial = next((value for key, value in canonical.items() if lowered in key), None)
        resolved.append(partial or name)
    return resolved


def _resolve_context_value(context_type, value):
    """Resolve a context value against the canonical lists for that context type."""
    value = (value or "").strip()
    if not value:
        return value
    category_map = {
        "location": "locations",
        "ppv": "ppvs",
        "fight_type": "fight_types",
        "brand": "brands",
        "championship": "championships",
    }
    category = category_map.get(context_type)
    if not category:
        return value
    canonical = {item.lower(): item for item in get_autocomplete_data(category)}
    lowered = value.lower()
    if lowered in canonical:
        return canonical[lowered]
    partial = next((item for key, item in canonical.items() if lowered in key), None)
    return partial or value


def _merge_unique_names(left, right):
    """Merge fighter lists while preserving order."""
    seen = set()
    merged = []
    for name in [*left, *right]:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            merged.append(name)
    return merged


def _suffix_for_plan(plan):
    """Build a conversational suffix for season/context scoping."""
    pieces = []
    context_type = plan.get("context_type")
    context_value = _resolve_context_value(context_type, plan.get("context_value", ""))
    if context_type == "location" and context_value:
        pieces.append(f"at {context_value}")
    elif context_type == "ppv" and context_value:
        pieces.append(f"at {context_value}")
    elif context_type == "fight_type" and context_value:
        pieces.append(f"in {context_value}")
    elif context_type == "brand" and context_value:
        pieces.append(f"on {context_value}")
    elif context_type == "championship" and context_value:
        pieces.append(f"for the {normalize_champ_name(context_value)}")
    elif context_type == "championship_matches":
        pieces.append("in championship matches")
    if plan.get("scope") == "season" and plan.get("season"):
        pieces.append(f"in Season {plan['season']}")
    return "" if not pieces else " " + " ".join(pieces)


def _describe_metric(metric, ranking):
    """Return a natural-language description for a metric/ranking pair."""
    if metric == "wins":
        return "most wins" if ranking == "top" else "fewest wins"
    if metric == "losses":
        return "most losses" if ranking == "top" else "fewest losses"
    if metric == "fights":
        return "most fights" if ranking == "top" else "fewest fights"
    if metric == "longest_win_streak":
        return "longest win streak" if ranking == "top" else "shortest longest win streak"
    return "best record" if ranking == "top" else "worst record"


def _serialize_rows(rows):
    """Serialize database rows for safe JSON responses."""
    return [{key: serialize_value(value) for key, value in row.items()} for row in rows[:50]]


def _render_debug_sql(sql, params):
    """Render debug SQL by replacing placeholders with readable values."""
    rendered = sql
    for value in params:
        rendered = rendered.replace("%s", str(value) if isinstance(value, (int, float)) else _sql_quote(value), 1)
    return rendered


def _sql_quote(value):
    """Render a basic SQL string literal for debug output only."""
    return "'" + str(value).replace("'", "''") + "'"


def _fmt_count(value):
    """Format whole-number stats without trailing decimal noise."""
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"-?\d+(\.0+)?", stripped):
            return str(int(float(stripped)))
        return stripped
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _validate_execution(plan, executed):
    """Reject obviously mismatched executions before returning an answer."""
    rows = executed.get("rows", [])
    if not rows:
        return
    query_type = plan.get("query_type")
    metric = plan.get("metric") or ""
    top = rows[0]
    if query_type == "rank_fighters" and metric in {"wins", "losses", "fights", "win_pct"}:
        required = {"fighter_name", "wins", "losses"}
        if not required.issubset(set(top.keys())):
            raise ValueError("Chat query returned an invalid fighter ranking shape.")
    if query_type == "rank_opponents":
        required = {"opponent", "wins", "losses"}
        if not required.issubset(set(top.keys())):
            raise ValueError("Chat query returned an invalid opponent ranking shape.")


def _legacy_sql_answer_question(client, model, question, history):
    """Fallback to the legacy SQL-generation path for unsupported questions."""
    history = (history or [])[-3:]
    messages = [{"role": "system", "content": _LEGACY_CHAT_SCHEMA}]
    for item in history:
        prior_question = str(item.get("question", ""))[:300]
        prior_sql = str(item.get("sql", ""))
        prior_rows = item.get("rows", [])
        messages.append({"role": "user", "content": prior_question})
        messages.append({"role": "assistant", "content": json.dumps({"sql": prior_sql, "explanation": f"Query returned {len(prior_rows)} rows: {json.dumps(prior_rows[:5])}"})})
    messages.append({"role": "user", "content": question})

    sql_resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=2048,
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
        current_app.logger.warning("[chat] legacy SQL error: %s | SQL: %s", db_err, sql)
        return {"answer": "I had trouble with that query — could you rephrase it more specifically?", "sql": sql, "rows": [], "status": 200}

    serialized = _serialize_rows(rows)
    answer_messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly, conversational sports stats assistant for a Super Smash Bros wrestling franchise. "
                "Do not mention SQL or databases. Keep responses casual and natural."
            ),
        },
        {"role": "user", "content": f"Question: {question}\n\nQuery used: {sql}\n\nResult rows ({len(serialized)} rows): {json.dumps(serialized)}"},
    ]
    answer_resp = client.chat.completions.create(
        model=model,
        messages=answer_messages,
        temperature=0.2,
        max_tokens=1024,
    )
    return {"answer": answer_resp.choices[0].message.content.strip(), "rows": serialized, "sql": sql, "status": 200}

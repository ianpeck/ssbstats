"""Tool-calling stats agent behind /api/chat.

The model gets the schema plus one tool, run_sql, and loops: query, read the
result, fix its query if the result looks wrong, then answer. Safety comes from
the database layer (read-only transaction, execution time limit, optional
SELECT-only user), with guard_sql as a cheap first filter.
"""

import json
import os
import re

from flask import current_app

from ssbstats_app.repositories.base import run_readonly_query, select_list
from ssbstats_app.services.chat_metadata import render_agent_prompt
from ssbstats_app.services.content import get_autocomplete_data
from ssbstats_app.utils import serialize_value

try:
    from openai import OpenAI as OpenAIClient
except ImportError:
    OpenAIClient = None

try:
    from groq import Groq as GroqClient
except ImportError:
    GroqClient = None


_GEMINI_MODEL = os.getenv("CHAT_GEMINI_MODEL", "gemini-2.5-flash")
_GROQ_MODEL = os.getenv("CHAT_GROQ_MODEL", "llama-3.3-70b-versatile")
_MAX_STEPS = 6
_MAX_QUESTION_CHARS = 500
_MAX_HISTORY_TURNS = 4
_ROWS_FOR_MODEL = 50
_ROWS_FOR_CLIENT = 50
_ALLOWED_PROCEDURES = {
    name.lower(): name
    for name in [
        "headtohead", "headtoheadSeason", "headtoheadLocation", "headtoheadFightType", "headtoheadPPV",
        "headtoheadChamp", "headtoheadMonth", "headtoheadAllFighters", "allFightsBetweenTwoFighters",
        "holistic", "statsbyseason",
    ]
}
_READ_ONLY_ERROR = "Only read-only queries are allowed."
_BANNED_SQL = ["into outfile", "into dumpfile", "load_file", "sleep(", "benchmark(", "get_lock(", "load data"]

_RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Run one read-only MySQL 8 query (SELECT, WITH ... SELECT, or CALL of a listed stored procedure) "
            "against the league database. Returns column names, up to 50 rows, and the total row count."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single read-only SQL statement."}},
            "required": ["sql"],
        },
    },
}

_GEMINI_CLIENT = None
_GROQ_CLIENT = None
_SYSTEM_PROMPT = None


def get_gemini_client():
    """Lazily initialize and return the Gemini client via its OpenAI-compatible endpoint."""
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


def _system_prompt():
    """Build the system prompt once, with live name lists so the model uses exact spellings."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        try:
            awards = select_list("SELECT Award_Name FROM Award ORDER BY Award_ID", 0)
        except Exception:
            awards = []
        vocabulary = {
            "Fighters": get_autocomplete_data("fighters"),
            "Championships": get_autocomplete_data("championships"),
            "Brands": get_autocomplete_data("brands"),
            "Fight types (FightLog.Description)": get_autocomplete_data("fight_types"),
            "PPVs": get_autocomplete_data("ppvs"),
            "Awards": awards,
            "Locations (stages)": get_autocomplete_data("locations"),
        }
        prompt = render_agent_prompt(vocabulary)
        if not vocabulary["Fighters"]:
            return prompt  # DB was unreachable; don't cache a prompt without names
        _SYSTEM_PROMPT = prompt
    return _SYSTEM_PROMPT


def guard_sql(sql):
    """Cheap pre-filter for model-written SQL. Returns (sql, error).

    This is not the security boundary: queries run in a read-only transaction
    with a time limit. It exists to reject obvious junk before a DB round trip.
    """
    sql = (sql or "").strip().rstrip(";").strip()
    lower = re.sub(r"\s+", " ", sql.lower())
    if not sql:
        return None, "Empty query."
    if len(sql) > 4000:
        return None, "Query too large."
    if ";" in sql:
        return None, "Only one statement is allowed."
    if "--" in sql or "/*" in sql or "#" in sql:
        return None, "Comments are not allowed."
    if any(pattern in lower for pattern in _BANNED_SQL):
        return None, "Disallowed SQL function."
    call = re.match(r"^call\s+(?:smashbros\.)?`?(\w+)`?\s*\(", lower)
    if call:
        if call.group(1) not in _ALLOWED_PROCEDURES:
            return None, "Unknown stored procedure."
        return sql, None
    if not re.match(r"^(select|with)\b", lower):
        return None, _READ_ONLY_ERROR
    misused = next((proc for proc in _ALLOWED_PROCEDURES if re.search(rf"\b(from|join)\s+(smashbros\.)?{proc}\s*\(", lower)), None)
    if misused:
        return None, (
            f"{_ALLOWED_PROCEDURES[misused]} is a stored procedure, not a table. Run it on its own, e.g. "
            f"CALL {_ALLOWED_PROCEDURES[misused]}('Fighter One', 'Fighter Two'), or query FightLog instead."
        )
    if re.search(r"\b(insert|update|delete|drop|alter|create|truncate|grant|rename)\b", lower):
        return None, _READ_ONLY_ERROR
    return sql, None


def answer_question(question, history):
    """Answer a natural-language stats question. Returns a dict with answer, rows, sql and status."""
    question = str(question or "").strip()[:_MAX_QUESTION_CHARS]
    if not question:
        return {"error": "No question provided.", "status": 400}

    gemini = get_gemini_client()
    client = gemini or get_groq_client()
    if not client:
        return {"error": "Chat is not configured right now.", "status": 503}
    model = _GEMINI_MODEL if gemini else _GROQ_MODEL

    try:
        return _run_agent(client, model, question, history)
    except Exception as exc:
        text = str(exc)
        if "429" in text or "rate_limit" in text.lower() or "quota" in text.lower():
            return {"answer": "The stats AI has hit its usage limit for now. Try again in a little while!", "rows": [], "sql": "", "status": 200}
        current_app.logger.exception("[chat] agent failure")
        return {"error": "Something went wrong answering that. Please try again.", "status": 500}


def _run_agent(client, model, question, history):
    """Run the tool-calling loop until the model answers or runs out of steps."""
    messages = [{"role": "system", "content": _system_prompt()}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": question})

    shown = {"rows": [], "sql": ""}
    last_failed = False
    nudged = False
    for _ in range(_MAX_STEPS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[_RUN_SQL_TOOL],
            temperature=0,
            max_tokens=2048,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            if last_failed and not nudged:
                # Models sometimes "answer" right after a failed query by guessing numbers.
                nudged = True
                messages.append({"role": "assistant", "content": message.content or ""})
                messages.append({"role": "user", "content": (
                    "Your last query failed, so you do not have that data yet. Fix the query and run it, "
                    "then answer. Only state numbers that came from a successful result."
                )})
                continue
            return _final(message.content, shown)

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
                for call in tool_calls
            ],
        })
        for call in tool_calls:
            result = _execute_tool_call(call, shown)
            # A blocked write is a deliberate refusal, not a query to fix.
            last_failed = "error" in result and result["error"] != _READ_ONLY_ERROR
            if last_failed:
                result["hint"] = "Fix the query and call run_sql again. Do not answer from this failed attempt."
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})

    # Out of steps: ask for the best answer from what it has already seen.
    messages.append({"role": "user", "content": "Answer now using only the results you already have."})
    response = client.chat.completions.create(model=model, messages=messages, temperature=0, max_tokens=1024)
    return _final(response.choices[0].message.content, shown)


def _execute_tool_call(call, shown):
    """Run one tool call and return a JSON-serializable result for the model."""
    if call.function.name != "run_sql":
        return {"error": f"Unknown tool {call.function.name}. Use run_sql."}
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return {"error": "Arguments were not valid JSON."}

    sql, guard_error = guard_sql(args.get("sql", ""))
    if guard_error:
        return {"error": guard_error}
    try:
        columns, rows, truncated = run_readonly_query(sql)
    except Exception as exc:
        current_app.logger.info("[chat] SQL error: %s | %s", exc, sql)
        return {"error": str(exc)[:500]}

    serialized = [{key: serialize_value(value) for key, value in row.items()} for row in rows]
    if serialized:
        shown["rows"], shown["sql"] = serialized[:_ROWS_FOR_CLIENT], sql
    return {
        "columns": columns,
        "rows": serialized[:_ROWS_FOR_MODEL],
        "row_count": f"{len(serialized)}+" if truncated else len(serialized),
    }


def _history_messages(history):
    """Turn client-supplied history into plain-text turns. Only text is trusted, never SQL."""
    messages = []
    for item in (history or [])[-_MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        prior_question = str(item.get("question", "")).strip()[:_MAX_QUESTION_CHARS]
        prior_answer = str(item.get("answer", "")).strip()[:800]
        if prior_question and prior_answer:
            messages.append({"role": "user", "content": prior_question})
            messages.append({"role": "assistant", "content": prior_answer})
    return messages


def _final(content, shown):
    """Package the model's final answer with the most recent result rows."""
    answer = (content or "").strip() or "I couldn't come up with an answer for that one. Try rephrasing it?"
    return {"answer": answer, "rows": shown["rows"], "sql": shown["sql"], "status": 200}

"""Conversation-state helpers for the stats chat agent."""

import re

from ssbstats_app.services.content import get_autocomplete_data


def build_chat_state(history):
    """Summarize the recent chat history into a lightweight reusable state."""
    state = {
        "fighter_names": [],
        "season": 0,
        "context_type": "",
        "context_value": "",
        "query_type": "",
        "metric": "",
        "ranking": "",
    }
    for item in history[-3:]:
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        extracted = extract_fighter_names(question)
        if extracted:
            state["fighter_names"] = _merge_unique_names(state["fighter_names"], extracted)
        season_match = re.search(r"\bseason\s+(\d+)\b", question, flags=re.IGNORECASE)
        if season_match:
            state["season"] = int(season_match.group(1))
        lower = question.lower()
        if "best record" in lower:
            state["metric"] = "win_pct"
            state["ranking"] = "top"
        elif "worst record" in lower:
            state["metric"] = "win_pct"
            state["ranking"] = "bottom"
        elif "most losses" in lower:
            state["metric"] = "losses"
            state["ranking"] = "top"
        elif "most wins" in lower:
            state["metric"] = "wins"
            state["ranking"] = "top"
        elif "most fights" in lower or "most matches" in lower:
            state["metric"] = "fights"
            state["ranking"] = "top"
        elif "longest win streak" in lower:
            state["metric"] = "longest_win_streak"
            state["ranking"] = "top"
        context_type, context_value = extract_context(question)
        if context_type:
            state["context_type"] = context_type
            state["context_value"] = context_value
        if "head-to-head" in lower or "head to head" in lower or " vs " in lower or " versus " in lower:
            state["query_type"] = "head_to_head"
        elif "what titles" in lower or "how many titles" in lower or "title reign" in lower:
            state["query_type"] = "title_history"
        elif "current champion" in lower or "who holds" in lower:
            state["query_type"] = "current_champions"
    return state


def apply_chat_state(plan, state, question):
    """Carry forward missing plan fields from recent conversation state."""
    lower = question.lower()
    if plan.get("query_type") == "generic_sql" and state.get("query_type") and _looks_like_follow_up(lower):
        plan["query_type"] = state["query_type"]
    if not plan.get("metric") and state.get("metric") and _looks_like_follow_up(lower):
        plan["metric"] = state["metric"]
    if not plan.get("ranking") and state.get("ranking") and _looks_like_follow_up(lower):
        plan["ranking"] = state["ranking"]
    if not plan.get("season") and state.get("season") and _references_previous_scope(lower):
        plan["season"] = state["season"]
        plan["scope"] = "season"
    if not plan.get("context_type") and state.get("context_type") and _references_previous_scope(lower):
        plan["context_type"] = state["context_type"]
        plan["context_value"] = state["context_value"]
    if not plan.get("fighter_names") and state.get("fighter_names") and _references_previous_subject(lower):
        plan["fighter_names"] = state["fighter_names"][:]
    return plan


def extract_fighter_names(question):
    """Extract likely fighter names from a question."""
    lower = question.lower()
    found = []
    for fighter in sorted(get_autocomplete_data("fighters"), key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(fighter.lower()) + r"(?!\w)"
        if re.search(pattern, lower):
            found.append(fighter)
    return found[:4]


def extract_context(question):
    """Infer a context type/value from the text using autocomplete vocab."""
    lower = question.lower()
    category_map = [
        ("location", "locations"),
        ("ppv", "ppvs"),
        ("fight_type", "fight_types"),
        ("brand", "brands"),
        ("championship", "championships"),
    ]
    for context_type, category in category_map:
        for item in sorted(get_autocomplete_data(category), key=len, reverse=True):
            if re.search(r"(?<!\w)" + re.escape(item.lower()) + r"(?!\w)", lower):
                return context_type, item
    if "championship match" in lower or "championship matches" in lower or "title matches" in lower:
        return "championship_matches", ""
    return "", ""


def _looks_like_follow_up(lower):
    """Return whether the message looks elliptical rather than standalone."""
    return any(
        phrase in lower
        for phrase in [
            "what about",
            "how about",
            "and in",
            "and at",
            "there",
            "that context",
            "that season",
        ]
    )


def _references_previous_scope(lower):
    """Return whether the question likely wants prior scope or context carried forward."""
    return _looks_like_follow_up(lower) or lower in {"there", "that season", "that context"}


def _references_previous_subject(lower):
    """Return whether the question likely refers to the prior named fighter(s)."""
    return _looks_like_follow_up(lower) or any(token in lower for token in ["them", "him", "her", "that fighter"])


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

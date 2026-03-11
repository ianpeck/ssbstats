import unittest
from unittest.mock import patch

from ssbstats_app.services.chat import guard_sql
from ssbstats_app.services.chat_state import apply_chat_state, build_chat_state


class GuardSqlTests(unittest.TestCase):
    """Cover the SQL safety checks used by the chat endpoint."""

    def test_rejects_non_select_queries(self):
        """Mutating SQL should be rejected outright."""
        sql, error = guard_sql("DELETE FROM Fighter")
        self.assertIsNone(sql)
        self.assertEqual(error, "Only SELECT queries are allowed.")

    def test_rejects_banned_patterns(self):
        """Known unsafe SQL constructs should be blocked."""
        sql, error = guard_sql("SELECT * FROM FightLog CROSS JOIN Fighter")
        self.assertIsNone(sql)
        self.assertEqual(error, "Disallowed SQL pattern detected.")

    def test_adds_default_limit_when_missing(self):
        """Queries without a limit should be capped automatically."""
        sql, error = guard_sql("SELECT * FROM careerstats")
        self.assertEqual(error, None)
        self.assertEqual(sql, "SELECT * FROM careerstats LIMIT 100")

    def test_preserves_existing_limit(self):
        """Queries that already limit results should be left alone."""
        sql, error = guard_sql("SELECT * FROM careerstats LIMIT 10")
        self.assertEqual(error, None)
        self.assertEqual(sql, "SELECT * FROM careerstats LIMIT 10")


class ChatStateTests(unittest.TestCase):
    """Cover conversation-state carry-forward behavior for the chat agent."""

    @patch("ssbstats_app.services.chat_state.get_autocomplete_data")
    def test_build_chat_state_extracts_recent_fighter_and_season(self, mock_autocomplete):
        """Recent questions should seed state for follow-up prompts."""
        mock_autocomplete.side_effect = lambda category: ["Mario", "Kirby"] if category == "fighters" else []

        state = build_chat_state(
            [
                {"question": "What is Mario's record in Season 6?"},
                {"question": "What about Kirby?"},
            ]
        )

        self.assertEqual(state["season"], 6)
        self.assertIn("Mario", state["fighter_names"])
        self.assertIn("Kirby", state["fighter_names"])

    def test_apply_chat_state_carries_forward_season_on_follow_up(self):
        """Elliptical follow-ups should inherit the prior season when omitted."""
        plan = {
            "query_type": "rank_fighters",
            "metric": "longest_win_streak",
            "ranking": "top",
            "scope": "all_time",
            "fighter_names": [],
            "season": 0,
            "minimum_sample": 0,
            "context_type": "",
            "context_value": "",
            "needs_clarification": False,
            "clarification_question": "",
        }
        state = {
            "fighter_names": ["Mario"],
            "season": 6,
            "context_type": "",
            "context_value": "",
            "query_type": "rank_fighters",
            "metric": "win_pct",
            "ranking": "top",
        }

        applied = apply_chat_state(plan, state, "What about in that season?")

        self.assertEqual(applied["season"], 6)
        self.assertEqual(applied["scope"], "season")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ssbstats_app import create_app
from ssbstats_app.services.chat import _history_messages, answer_question, guard_sql


class GuardSqlTests(unittest.TestCase):
    """Cover the cheap SQL pre-filter used before the read-only DB layer."""

    def test_allows_select_and_with(self):
        """Plain reads and CTE reads should pass through unchanged (minus a trailing semicolon)."""
        self.assertEqual(guard_sql("SELECT * FROM careerstats;"), ("SELECT * FROM careerstats", None))
        sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
        self.assertEqual(guard_sql(sql), (sql, None))

    def test_allows_replace_function(self):
        """REPLACE() is a common string function for win percentages, not a write."""
        sql = "SELECT CAST(REPLACE(`Win Percentage`, '%', '') AS DECIMAL(5,2)) FROM careerstats"
        self.assertIsNone(guard_sql(sql)[1])

    def test_rejects_writes(self):
        """Mutating SQL, including writes hidden behind a CTE, should be rejected."""
        for sql in ["DELETE FROM Elo", "WITH t AS (SELECT 1) DELETE FROM Elo", "UPDATE Fighter SET Brand_ID = 1"]:
            self.assertIsNone(guard_sql(sql)[0], sql)

    def test_rejects_multiple_statements_and_comments(self):
        """Stacked statements and comment tricks should be rejected."""
        self.assertIsNone(guard_sql("SELECT 1; SELECT 2")[0])
        self.assertIsNone(guard_sql("SELECT 1 -- hi")[0])

    def test_only_known_procedures(self):
        """CALL is limited to the league's read-only stored procedures."""
        self.assertIsNone(guard_sql("CALL SmashBros.headtohead('Mario', 'Kirby')")[1])
        self.assertIsNotNone(guard_sql("CALL mysql.something()")[1])

    def test_procedure_used_as_table_gets_helpful_error(self):
        """Selecting FROM a procedure should explain how to CALL it."""
        error = guard_sql("SELECT Wins FROM headtoheadChamp('Kirby', 'Fox')")[1]
        self.assertIn("CALL headtoheadChamp(", error)


class HistoryTests(unittest.TestCase):
    """Client history is replayed as plain text only."""

    def test_history_keeps_question_answer_text_only(self):
        """SQL or rows sent by the client should never reach the model."""
        messages = _history_messages([{"question": "Who is best?", "answer": "**Kirby**.", "sql": "DROP TABLE x"}, "junk"])
        self.assertEqual(messages, [{"role": "user", "content": "Who is best?"}, {"role": "assistant", "content": "**Kirby**."}])


def _tool_call_response(sql):
    call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="run_sql", arguments=json.dumps({"sql": sql})))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))])


def _text_response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


class AgentLoopTests(unittest.TestCase):
    """Cover the tool-calling loop with a fake model and fake database."""

    def setUp(self):
        self.app = create_app()

    @patch("ssbstats_app.services.chat._system_prompt", return_value="system")
    @patch("ssbstats_app.services.chat.run_readonly_query")
    @patch("ssbstats_app.services.chat.get_gemini_client")
    def test_runs_query_then_answers(self, mock_gemini, mock_query, _prompt):
        """The model's query result should be fed back, and the rows returned alongside the answer."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _tool_call_response("SELECT Fighter_Name FROM careerstats LIMIT 1"),
            _text_response("**Kirby** leads."),
        ]
        mock_gemini.return_value = client
        mock_query.return_value = (["Fighter_Name"], [{"Fighter_Name": "Kirby"}], False)

        with self.app.app_context():
            result = answer_question("Who leads?", [])

        self.assertEqual(result["answer"], "**Kirby** leads.")
        self.assertEqual(result["rows"], [{"Fighter_Name": "Kirby"}])
        self.assertEqual(result["sql"], "SELECT Fighter_Name FROM careerstats LIMIT 1")
        tool_message = client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertIn("Kirby", tool_message["content"])

    @patch("ssbstats_app.services.chat._system_prompt", return_value="system")
    @patch("ssbstats_app.services.chat.run_readonly_query")
    @patch("ssbstats_app.services.chat.get_gemini_client")
    def test_blocked_sql_is_reported_to_model_not_run(self, mock_gemini, mock_query, _prompt):
        """A write attempt should come back to the model as an error and never touch the DB."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _tool_call_response("DELETE FROM Elo"),
            _text_response("I can only read stats."),
        ]
        mock_gemini.return_value = client

        with self.app.app_context():
            result = answer_question("Delete the Elo table", [])

        mock_query.assert_not_called()
        self.assertEqual(result["answer"], "I can only read stats.")
        tool_message = client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]
        self.assertIn("error", json.loads(tool_message["content"]))

    @patch("ssbstats_app.services.chat._system_prompt", return_value="system")
    @patch("ssbstats_app.services.chat.run_readonly_query")
    @patch("ssbstats_app.services.chat.get_gemini_client")
    def test_answer_after_failed_query_is_sent_back(self, mock_gemini, mock_query, _prompt):
        """If the model answers right after a SQL error, it must retry instead of guessing."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _tool_call_response("SELECT * FROM headtoheadChamp('A', 'B')"),
            _text_response("A is 2-1."),
            _tool_call_response("CALL headtoheadChamp('A', 'B')"),
            _text_response("A is 4-3."),
        ]
        mock_gemini.return_value = client
        mock_query.return_value = (["Fighter One Wins"], [{"Fighter One Wins": "4"}], False)

        with self.app.app_context():
            result = answer_question("A vs B in title matches?", [])

        self.assertEqual(result["answer"], "A is 4-3.")
        self.assertEqual(mock_query.call_count, 1)

    def test_empty_question_is_rejected(self):
        """Blank input should fail fast without any model call."""
        result = answer_question("   ", [])
        self.assertEqual(result["status"], 400)


if __name__ == "__main__":
    unittest.main()

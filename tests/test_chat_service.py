import unittest

from ssbstats_app.services.chat import guard_sql


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


if __name__ == "__main__":
    unittest.main()


import os
import tempfile
import unittest
from datetime import datetime

from ssbstats_app.security import DailyQuota


class DailyQuotaTests(unittest.TestCase):
    """Cover the shared daily chat caps."""

    def setUp(self):
        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.now = datetime(2026, 10, 1, 12, 0)

    def tearDown(self):
        os.remove(self.path)

    def quota(self, per_visitor=3, total=5):
        return DailyQuota(per_visitor=per_visitor, total=total, path=self.path, clock=lambda: self.now)

    def test_per_visitor_limit(self):
        """A visitor is stopped after their own daily allowance."""
        quota = self.quota()
        self.assertEqual([quota.consume("1.1.1.1") for _ in range(4)], [None, None, None, "visitor"])

    def test_site_wide_limit_applies_across_visitors(self):
        """Once the site-wide total is used up, everyone is stopped."""
        quota = self.quota()
        results = [quota.consume(f"10.0.0.{i}") for i in range(6)]
        self.assertEqual(results, [None] * 5 + ["total"])

    def test_counts_are_shared_between_workers(self):
        """Two instances (like two gunicorn workers) share one count through the file."""
        worker_a, worker_b = self.quota(), self.quota()
        for _ in range(3):
            worker_a.consume("2.2.2.2")
        self.assertEqual(worker_b.consume("2.2.2.2"), "visitor")

    def test_resets_on_a_new_day(self):
        """Counts start over after midnight."""
        quota = self.quota()
        for _ in range(3):
            quota.consume("3.3.3.3")
        self.assertEqual(quota.consume("3.3.3.3"), "visitor")
        self.now = datetime(2026, 10, 2, 0, 1)
        self.assertIsNone(quota.consume("3.3.3.3"))


if __name__ == "__main__":
    unittest.main()

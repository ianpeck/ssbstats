import time
import unittest
from unittest.mock import patch

from ssbstats_app.cache import ttl_cache


class TtlCacheTests(unittest.TestCase):
    """Cover the stale-while-revalidate payload cache."""

    def test_caches_per_argument(self):
        """Repeat calls with the same argument should not recompute."""
        calls = []

        @ttl_cache(60)
        def build(name):
            calls.append(name)
            return {"name": name}

        self.assertEqual(build("Kirby"), {"name": "Kirby"})
        build("Kirby")
        build("Fox")
        self.assertEqual(calls, ["Kirby", "Fox"])

    def test_results_built_during_query_failures_are_not_cached(self):
        """A payload assembled while a query failed should be rebuilt next time."""
        counter = {"failures": 0}
        calls = []

        @ttl_cache(60)
        def build(name):
            calls.append(name)
            counter["failures"] += 1  # simulate a swallowed query error during the build
            return {"name": name, "titles": []}

        with patch("ssbstats_app.cache.query_failure_count", side_effect=lambda: counter["failures"]):
            build("Kirby")
            build("Kirby")
        self.assertEqual(len(calls), 2)

    def test_stale_entry_is_served_then_refreshed_in_background(self):
        """Once stale, callers still get the old value immediately while a refresh runs."""
        version = {"n": 1}

        @ttl_cache(0.05)
        def build():
            return version["n"]

        self.assertEqual(build(), 1)
        version["n"] = 2
        time.sleep(0.1)
        self.assertEqual(build(), 1)  # stale value, refresh kicked off
        time.sleep(0.1)
        self.assertEqual(build(), 2)

    def test_refresh_rebuilds_immediately(self):
        """refresh() should recompute and store a new value even while the entry is fresh."""
        version = {"n": 1}

        @ttl_cache(60)
        def build(name):
            return (name, version["n"])

        build("Kirby")
        version["n"] = 2
        build.refresh("Kirby")
        self.assertEqual(build("Kirby"), ("Kirby", 2))

    def test_copy_result_protects_cached_value(self):
        """Mutating a returned copy must not change what later callers get."""
        @ttl_cache(60, copy_result=True)
        def build():
            return {"scores": [1, 2]}

        build()["scores"].append(3)
        self.assertEqual(build(), {"scores": [1, 2]})


if __name__ == "__main__":
    unittest.main()

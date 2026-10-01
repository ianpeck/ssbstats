import threading
import time
import unittest
from unittest.mock import patch

from ssbstats_app.repositories import base


class QueryConcurrencyTests(unittest.TestCase):
    """The per-process query cap keeps us under the database's connection limit."""

    def test_never_more_than_the_cap_run_at_once(self):
        """Extra callers should wait for a slot rather than run concurrently."""
        state = {"now": 0, "peak": 0}
        lock = threading.Lock()

        @base._limit_concurrency
        def fake_query():
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1

        with patch.object(base, "_query_slots", threading.BoundedSemaphore(2)):
            threads = [threading.Thread(target=fake_query) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(state["peak"], 2)


if __name__ == "__main__":
    unittest.main()

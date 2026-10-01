"""Small in-process cache for read-heavy payloads that only change when fights are entered."""

import copy
import logging
import threading
import time
from functools import wraps

from ssbstats_app.repositories.base import query_failure_count


logger = logging.getLogger(__name__)


def ttl_cache(seconds, copy_result=False):
    """Cache a function's result per positional arguments, stale-while-revalidate style.

    - Fresh entries are returned immediately.
    - Stale entries are also returned immediately, and refreshed in a background thread,
      so visitors never wait on a rebuild once a key has been computed.
    - Results built while any query failed are not stored, so a transient DB error
      can't pin a half-empty payload in the cache.
    - copy_result=True returns a deep copy, for callers that might mutate the result.
    - wrapper.refresh(*args) rebuilds an entry now (used by the background warmer).
    """
    def decorate(func):
        entries = {}
        refreshing = set()
        lock = threading.Lock()

        def compute(key):
            failures_before = query_failure_count()
            value = func(*key)
            if query_failure_count() == failures_before:
                with lock:
                    entries[key] = (value, time.time())
            return value

        def refresh(key):
            try:
                compute(key)
            except Exception:
                logger.exception("Background refresh failed for %s%s", func.__name__, key)
            finally:
                with lock:
                    refreshing.discard(key)

        @wraps(func)
        def wrapper(*args):
            key = tuple(args)
            with lock:
                entry = entries.get(key)
                if entry and time.time() - entry[1] > seconds and key not in refreshing:
                    refreshing.add(key)
                    threading.Thread(target=refresh, args=(key,), daemon=True).start()
            value = entry[0] if entry else compute(key)
            return copy.deepcopy(value) if copy_result else value

        wrapper.refresh = lambda *args: compute(tuple(args))
        wrapper.cache_clear = entries.clear
        return wrapper

    return decorate

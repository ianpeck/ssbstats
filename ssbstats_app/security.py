"""Request-level security helpers: client IP, admin allowlist, rate limiting, safe redirects."""

import fcntl
import json
import os
import tempfile
import threading
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
    _QUOTA_TZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - tz database missing
    _QUOTA_TZ = None

from flask import current_app, request


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def get_client_ip():
    """Return the visitor's IP.

    Cloudflare sets CF-Connecting-IP. X-Forwarded-For is ignored because its first
    entry is whatever the client sent. Behind EB's nginx, remote_addr is loopback,
    so requests that bypass Cloudflare all look like one client (which is fine for
    rate limiting and is never treated as trusted).
    """
    return (request.headers.get("CF-Connecting-IP") or request.remote_addr or "").strip()


def admin_ips():
    """Return the configured admin IP allowlist (empty set means no IP restriction)."""
    raw = (os.getenv("ADMIN_ALLOWED_IPS") or "").strip()
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def admin_ip_allowed():
    """Return whether the current request may reach admin pages.

    Loopback is only trusted in debug mode: in production, nginx proxies every
    request from loopback, so trusting it would disable the allowlist.
    """
    allowed = admin_ips()
    if not allowed:
        return True
    ip = get_client_ip()
    if ip in _LOOPBACK and current_app.debug:
        return True
    return ip in allowed


def safe_next_url(target, fallback):
    """Only allow same-site relative redirects (blocks ?next=https://evil.example)."""
    if not target:
        return fallback
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return fallback
    return target


class RateLimiter:
    """Sliding-window limiter keyed by client IP.

    In-memory and per-process, so with N gunicorn workers the effective limit is
    up to N times higher. Good enough to stop casual abuse of a hobby site.
    """

    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, key=None):
        """Record a request and return True if it should be rejected."""
        key = key or get_client_ip() or "unknown"
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window]
            limited = len(recent) >= self.limit
            if not limited:
                recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > 5000:
                self._prune(now)
            return limited

    def _prune(self, now):
        """Drop keys with no recent hits so memory stays bounded."""
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[key]


class DailyQuota:
    """Per-visitor and site-wide daily caps, shared by every gunicorn worker on the host.

    Workers don't share memory, so counts live in a small JSON file guarded by an
    exclusive file lock. Counts reset at midnight US Eastern.
    """

    def __init__(self, per_visitor, total, path=None, clock=None):
        self.per_visitor = per_visitor
        self.total = total
        self.path = path or os.getenv("CHAT_QUOTA_FILE") or os.path.join(tempfile.gettempdir(), "ssbstats_chat_quota.json")
        self.clock = clock or (lambda: datetime.now(_QUOTA_TZ))

    def consume(self, key):
        """Count one question for key. Returns None if allowed, else "visitor" or "total"."""
        today = self.clock().date().isoformat()
        with open(self.path, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.seek(0)
                try:
                    state = json.loads(handle.read() or "{}")
                except ValueError:
                    state = {}
                if state.get("date") != today:
                    state = {"date": today, "total": 0, "visitors": {}}
                if state["total"] >= self.total:
                    return "total"
                if state["visitors"].get(key, 0) >= self.per_visitor:
                    return "visitor"
                state["total"] += 1
                state["visitors"][key] = state["visitors"].get(key, 0) + 1
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(state))
                return None
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


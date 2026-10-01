import os
import threading
from functools import wraps
from pathlib import Path

import pymysql
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path("secrets.env"))


def _env_first(*names):
    """Return the first populated environment variable from the provided names."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _build_connection(user_env_var, password_env_var):
    """Create a new MySQL connection for the requested credential pair."""
    return pymysql.connect(
        host=os.getenv("awsendpoint"),
        database=os.getenv("awsdb"),
        user=_env_first(user_env_var, "awswriteuser" if user_env_var == "write_username" else user_env_var),
        password=_env_first(password_env_var, "awswritepassword" if password_env_var == "write_password" else password_env_var),
        port=3306,
        # Without these, a stalled network read blocks a gunicorn worker indefinitely.
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


def get_connection():
    """Create a new MySQL connection using the default read credentials."""
    return _build_connection("awsuser", "awspassword")


def get_write_connection():
    """Create a new MySQL connection using the scheduling/admin write credentials."""
    return _build_connection("write_username", "write_password")


def get_chat_connection():
    """Create a connection for AI-generated SQL, preferring a dedicated SELECT-only user."""
    if os.getenv("awschatuser"):
        return _build_connection("awschatuser", "awschatpassword")
    return get_connection()


def run_readonly_query(query, max_rows=200, timeout_ms=5000):
    """Run untrusted SQL inside a read-only transaction with a server-side time limit.

    Returns (columns, rows, truncated). Writes fail at the MySQL level regardless of
    the user's grants, and the transaction is always rolled back.
    """
    conn = get_chat_connection()
    try:
        cur = conn.cursor()
        cur.execute("SET SESSION MAX_EXECUTION_TIME = %s", (int(timeout_ms),))
        cur.execute("START TRANSACTION READ ONLY")
        cur.execute(query)
        cols = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(max_rows + 1) if cols else []
        rows = [dict(zip(cols, row)) for row in fetched[:max_rows]]
        return cols, rows, len(fetched) > max_rows
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


_failures = {"count": 0}
_failures_lock = threading.Lock()


def query_failure_count():
    """Return how many queries have raised so far. Caches compare it before and after
    building a payload, because several repositories turn query errors into empty lists."""
    return _failures["count"]


def _track_failures(func):
    """Count query exceptions (then re-raise them unchanged)."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            with _failures_lock:
                _failures["count"] += 1
            raise

    return wrapper


@_track_failures
def h2h_query_sql(query, params=None):
    """Execute an H2H stored procedure and reshape its row into fighter dicts."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        fighter_data = cur.fetchone()
        if not fighter_data:
            return [
                {"Fighter": "", "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
                {"Fighter": "", "Wins": "0", "Losses": "0", "W/L %": "0.00%"},
            ]
        f1, f2 = {}, {}
        for i, data in enumerate(fighter_data):
            if i == 0:
                f1["Fighter"] = data
            elif i == 1:
                f1["Wins"] = str(data)
                f2["Losses"] = str(data)
            elif i == 2:
                f1["W/L %"] = data
            elif i == 3:
                f2["Fighter"] = data
            elif i == 4:
                f2["Wins"] = str(data)
                f1["Losses"] = str(data)
            elif i == 5:
                f2["W/L %"] = data
        return [f1, f2]
    finally:
        conn.close()


@_track_failures
def select_list(query, columnnumber, params=None):
    """Execute a query and return one column from every result row."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return [row[columnnumber] for row in cur.fetchall()]
    finally:
        conn.close()


@_track_failures
def select_view_row(query, params=None):
    """Execute a query and return the raw tuple rows."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return list(cur.fetchall())
    finally:
        conn.close()


@_track_failures
def select_view_dicts(query, params=None):
    """Execute a query and return rows as dictionaries keyed by column name."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def execute_write(query, params=None):
    """Execute a single write statement and return the last insert id."""
    conn = get_write_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def nk(name):
    """Normalize a fighter name to a lowercase stripped lookup key."""
    return (name or "").lower().strip()

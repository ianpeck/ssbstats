import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path("secrets.env"))


def get_connection():
    """Create a new MySQL connection using environment-based credentials."""
    return pymysql.connect(
        host=os.getenv("awsendpoint"),
        database=os.getenv("awsdb"),
        user=os.getenv("awsuser"),
        password=os.getenv("awspassword"),
        port=3306,
    )


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


def select_list(query, columnnumber, params=None):
    """Execute a query and return one column from every result row."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return [row[columnnumber] for row in cur.fetchall()]
    finally:
        conn.close()


def select_view_row(query, params=None):
    """Execute a query and return the raw tuple rows."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params) if params else cur.execute(query)
        return list(cur.fetchall())
    finally:
        conn.close()


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


def nk(name):
    """Normalize a fighter name to a lowercase stripped lookup key."""
    return (name or "").lower().strip()

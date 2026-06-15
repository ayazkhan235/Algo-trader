import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        from paper_trading.sqlite_engine import DB_PATH, _ensure_dir
        _ensure_dir()
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        return con

def placeholder():
    return "%s" if DATABASE_URL else "?"

def is_postgres():
    return bool(DATABASE_URL)

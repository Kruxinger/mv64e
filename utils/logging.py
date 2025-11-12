# utils/logging.py
import psycopg2
import os
from datetime import datetime

DB_HOST = os.environ.get("POSTGRES_HOST", "db")
DB_NAME = os.environ.get("POSTGRES_DB", "onco")
DB_USER = os.environ.get("POSTGRES_USER", "onco_user")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "onco_pass")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def log_entry(case_id, pat_id, level, message):
    """Schreibt einen Logeintrag in die Datenbank."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO logs (case_id, pat_id, type, text)
            VALUES (%s, %s, %s, %s)
        """, (case_id, pat_id, level, message))
        conn.commit()
    except Exception as e:
        print(f"[DB-LOGGING-ERROR] {e}")
    finally:
        cur.close()
        conn.close()

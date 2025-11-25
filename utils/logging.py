# utils/logging.py
import psycopg2
import os
from typing import Literal

from datetime import datetime

from flask import flash

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
def flash_msg(case_id, pat_id, level: Literal["success","info","error","warning"], message):
    flash_msg = message
    if case_id not in ("", None) or pat_id not in ("", None):
        flash_msg += " (<placeholder_case> | <placeholder_pat>)"
    if case_id not in ("", None):
        flash_msg = flash_msg.replace("<placeholder_case>", f"CaseID: {case_id}")
    else:
        flash_msg = flash_msg.replace("<placeholder_case>", "")
    if pat_id not in ("", None):
        flash_msg = flash_msg.replace("<placeholder_case>", f"PatID: {pat_id}")
    else:
        flash_msg = flash_msg.replace("<placeholder_case>", "")
    flash(flash_msg, category=level)

def log_entry_and_flash(case_id, pat_id, level: Literal["success", "info", "error", "warning"], message, do_flash=False):
    if do_flash:
        flash_msg(case_id, pat_id, level, message)
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






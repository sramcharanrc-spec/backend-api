# app/rcm/store.py

import sqlite3
from datetime import datetime
import threading

DB_PATH = "app/rcm/rcm_dev.sqlite"
_db_lock = threading.Lock()


# -------------------------
# DB CONNECTION
# -------------------------
def get_conn():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


# -------------------------
# INIT DB
# -------------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id TEXT PRIMARY KEY,
            claim_id TEXT,
            status TEXT NOT NULL,
            transmission_id TEXT,
            raw_edi TEXT,
            ack_type TEXT,
            status_history text,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# MUST RUN ON IMPORT
init_db()


# -------------------------
# UPSERT SUBMISSION
# -------------------------
def save_submission(
    submission_id: str,
    claim_id: str | None,
    status: str,
    transmission_id: str | None,
    raw_edi: str,
    ack_type: str | None = None
):
    now = datetime.utcnow().isoformat()

    with _db_lock:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO submissions (
                submission_id,
                claim_id,
                status,
                transmission_id,
                raw_edi,
                ack_type,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(submission_id) DO UPDATE SET
                claim_id = COALESCE(excluded.claim_id, submissions.claim_id),
                status = excluded.status,
                transmission_id = COALESCE(excluded.transmission_id, submissions.transmission_id),
                raw_edi = CASE
                    WHEN excluded.raw_edi != '' THEN excluded.raw_edi
                    ELSE submissions.raw_edi
                END,
                ack_type = COALESCE(excluded.ack_type, submissions.ack_type),
                updated_at = excluded.updated_at
        """, (
            submission_id,
            claim_id,
            status,
            transmission_id,
            raw_edi,
            ack_type,
            now,
            now
        ))

        conn.commit()
        conn.close()


# -------------------------
# FETCH SINGLE SUBMISSION
# -------------------------
def get_submission(submission_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            submission_id,
            claim_id,
            status,
            transmission_id,
            raw_edi,
            ack_type,
            created_at,
            updated_at
        FROM submissions
        WHERE submission_id = ?
    """, (submission_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return dict(row)


# -------------------------
# FETCH ALL SUBMISSIONS
# -------------------------
def get_all_submissions():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            submission_id,
            claim_id,
            status,
            transmission_id,
            raw_edi,
            ack_type,
            created_at,
            updated_at
        FROM submissions
    """)

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_submission_by_claim_id(claim_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM submissions
        WHERE claim_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (claim_id,))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None
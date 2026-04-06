# app/rcm/store.py
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from .models import Submission, ClaimStatus

DB_PATH = os.path.join(os.path.dirname(__file__), "rcm_dev.sqlite")


def _get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            raw_edi TEXT NOT NULL,
            denial_reason TEXT
        )
        """
    )
    conn.commit()
    conn.close()


# initialize on import
init_db()


def save_submission(sub: Submission) -> None:
    """
    Persist a Submission dataclass to the SQLite DB.
    Uses the `denial_reason` column to match Submission.denial_reason.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO submissions
        (id, claim_id, created_at, status, raw_edi, denial_reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            sub.id,
            sub.claim_id,
            sub.created_at.isoformat(),
            sub.status.value,
            sub.raw_edi,
            sub.denial_reason,
        ),
    )
    conn.commit()
    conn.close()


def load_submission(submission_id: str) -> Optional[Submission]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM submissions WHERE id = ?",
        (submission_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return Submission(
        id=row["id"],
        claim_id=row["claim_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        status=ClaimStatus(row["status"]),
        raw_edi=row["raw_edi"],
        denial_reason=row["denial_reason"],
    )


def list_submissions(limit: int = 50) -> List[Submission]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM submissions ORDER BY datetime(created_at) DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        Submission(
            id=row["id"],
            claim_id=row["claim_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=ClaimStatus(row["status"]),
            raw_edi=row["raw_edi"],
            denial_reason=row["denial_reason"],
        )
        for row in rows
    ]

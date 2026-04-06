import sqlite3
import json
from datetime import datetime

DB_PATH = "app/rcm/rcm_dev.sqlite"


# -------------------------
# SAVE CLAIM
# -------------------------
def save_claim(claim_id: str, claim_json: dict):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO claims (
            claim_id,
            payload,
            created_at
        ) VALUES (?, ?, ?)
    """, (
        claim_id,
        json.dumps(claim_json),
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


# -------------------------
# GET CLAIM
# -------------------------
def get_claim(claim_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT payload
        FROM claims
        WHERE claim_id = ?
    """, (claim_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return json.loads(row[0])

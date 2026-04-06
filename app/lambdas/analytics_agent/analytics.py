# app/rcm/analytics.py

import sqlite3

DB_PATH = "app/rcm/rcm_dev.sqlite"


def _get_conn():
    return sqlite3.connect(DB_PATH)


def get_kpis():
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM submissions")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM submissions WHERE status = 'SUBMITTED'")
    submitted = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM submissions WHERE status = 'DENIED'")
    denied = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM submissions WHERE status LIKE '%PAID%'")
    paid = cur.fetchone()[0]

    conn.close()

    return {
        "total_claims": total,
        "submitted": submitted,
        "denied": denied,
        "paid": paid
    }


def analytics_dashboard():
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT status, COUNT(*)
        FROM submissions
        GROUP BY status
    """)

    rows = cur.fetchall()
    conn.close()

    return {
        "status_breakdown": [
            {"status": r[0], "count": r[1]}
            for r in rows
        ]
    }

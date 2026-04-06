# app/rcm/reconciliation.py

from app.lambdas.Shared.store import get_conn


def reconciliation_report():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT status, COUNT(*)
        FROM submissions
        WHERE status IN ('PAID', 'UNDERPAID')
        GROUP BY status
    """)

    rows = cur.fetchall()
    conn.close()

    report = {status: count for status, count in rows}
    report["total_reconciled"] = sum(report.values())

    return report

from __future__ import annotations

from app.lambdas.Shared.store import get_all_submissions


def get_kpis() -> dict:
    submissions = get_all_submissions()
    total = len(submissions)
    paid = sum(1 for item in submissions if item.get("status") == "PAID")
    denied = sum(1 for item in submissions if item.get("status") == "DENIED")
    return {
        "total_submissions": total,
        "paid_count": paid,
        "denied_count": denied,
        "payment_rate": paid / total if total else 0,
        "denial_rate": denied / total if total else 0,
    }


def analytics_dashboard() -> dict:
    return {
        "kpis": get_kpis(),
        "submissions": get_all_submissions(),
    }

from __future__ import annotations

from app.lambdas.Shared.store import get_all_submissions


def reconciliation_report() -> dict:
    submissions = get_all_submissions()
    return {
        "total_submissions": len(submissions),
        "paid": sum(1 for item in submissions if item.get("status") == "PAID"),
        "denied": sum(1 for item in submissions if item.get("status") == "DENIED"),
        "open": sum(1 for item in submissions if item.get("status") not in {"PAID", "DENIED"}),
    }


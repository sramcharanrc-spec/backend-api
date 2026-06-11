from __future__ import annotations


def post_payment(payload: dict) -> dict:
    amount = payload.get("paid_amount", payload.get("amount", payload.get("payment_amount", 0)))
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0

    return {
        "submission_id": payload.get("submission_id", "UNKNOWN"),
        "claim_id": payload.get("claim_id"),
        "status": "PAID" if amount > 0 else payload.get("status", "PAYMENT_POSTED"),
        "paid_amount": amount,
    }


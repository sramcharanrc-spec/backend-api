def reconcile_payment(claim, payment_data):

    expected = payment_data.get("expected_amount", claim.get("total_charge", 0))
    received = payment_data.get("paid_amount", 0)

    if received < expected:
        status = "partial"
    elif received > expected:
        status = "overpaid"
    else:
        status = "paid"

    return {
        "expected": expected,
        "received": received,
        "status": status
    }
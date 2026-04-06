from ...rcm.alerts import detect_underpayment
from app.lambdas.Shared.store import save_submission


def post_payment(payload: dict):
    """
    payload:
    {
      "submission_id": "...",
      "expected_amount": 1000,
      "paid_amount": 800
    }
    """

    #  Validation (prevents KeyError)
    required_fields = ["submission_id", "expected_amount", "paid_amount"]
    missing = [f for f in required_fields if f not in payload]

    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    submission_id = payload["submission_id"]
    expected = float(payload["expected_amount"])
    paid = float(payload["paid_amount"])

    #  Business logic
    variance = expected - paid
    alert = detect_underpayment(expected, paid)

    if paid == expected:
        status = "PAID"
    elif paid < expected:
        status = "UNDERPAID"
    else:
        status = "OVERPAID"

    #  Persist payment outcome
    save_submission(
        submission_id=submission_id,
        claim_id=None,
        status=status,
        transmission_id="835-AUTO",
        raw_edi=f"EXPECTED:{expected}|PAID:{paid}|VARIANCE:{variance}",
        ack_type="835"
    )

    # Response
    return {
        "submission_id": submission_id,
        "status": status,
        "expected": expected,
        "paid": paid,
        "variance": variance,
        "alert": alert
    }

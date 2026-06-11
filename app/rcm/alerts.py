UNDERPAYMENT_THRESHOLD_PERCENT = 5


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = (
                value
                .replace("$", "")
                .replace(",", "")
                .replace("USD", "")
                .strip()
            )

        if value == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def detect_underpayment(expected, paid, threshold_percent=UNDERPAYMENT_THRESHOLD_PERCENT):
    expected = safe_float(expected, 0.0)
    paid = safe_float(paid, 0.0)

    if expected <= 0:
        return {
            "alert": False,
            "type": "UNDERPAYMENT",
            "variance": 0,
            "percent": 0,
            "underpaid": False,
            "expected_amount": expected,
            "received_amount": paid,
            "difference": 0.0,
            "underpayment_rate": 0.0,
            "reason": "Expected amount is missing or zero",
        }

    variance = round(expected - paid, 2)
    underpaid = variance > 0.01
    underpayment_rate = round(variance / expected, 4) if underpaid else 0.0
    percent = round((variance / expected) * 100, 2)

    if percent >= threshold_percent:
        return {
            "alert": True,
            "type": "UNDERPAYMENT",
            "variance": variance,
            "percent": percent,
            "threshold_percent": threshold_percent,
            "underpaid": underpaid,
            "expected_amount": expected,
            "received_amount": paid,
            "difference": variance if underpaid else 0.0,
            "underpayment_rate": underpayment_rate,
            "message": f"Payment is under expected amount by {percent}%",
        }

    return {
        "alert": False,
        "type": "UNDERPAYMENT",
        "variance": variance,
        "percent": percent,
        "threshold_percent": threshold_percent,
        "underpaid": underpaid,
        "expected_amount": expected,
        "received_amount": paid,
        "difference": variance if underpaid else 0.0,
        "underpayment_rate": underpayment_rate,
    }

UNDERPAYMENT_THRESHOLD_PERCENT = 5  # configurable

def detect_underpayment(expected, paid):
    variance = expected - paid
    percent = (variance / expected) * 100 if expected else 0

    if percent >= UNDERPAYMENT_THRESHOLD_PERCENT:
        return {
            "alert": True,
            "type": "UNDERPAYMENT",
            "variance": variance,
            "percent": round(percent, 2)
        }

    return {"alert": False}

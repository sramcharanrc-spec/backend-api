DENIAL_RULES = {
    "CO-50": "Check medical necessity & diagnosis",
    "CO-97": "Missing or invalid modifier",
    "CO-16": "Missing information"
}

def predict_denial(payload: dict) -> dict:
    """
    Uses rules today, ML tomorrow
    """
    for code in payload.get("diagnosis_codes", []):
        if code.startswith("Z"):
            return {
                "risk": "HIGH",
                "reason": "Non-covered diagnosis"
            }

    return {
        "risk": "LOW",
        "reason": "No known denial patterns"
    }

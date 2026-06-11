def calculate_confidence(source, claim):
    score = 0.0

    # Base score
    if source == "AI":
        score += 0.7
    elif source == "FALLBACK":
        score += 0.4

    # Data completeness
    if claim.get("cpt_codes"):
        score += 0.1

    if claim.get("services"):
        score += 0.1

    if claim.get("patient", {}).get("name"):
        score += 0.1

    return round(min(score, 1.0), 2)


def normalize_confidence_score(value):
    if value in (None, "", [], {}):
        return None

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None

    if confidence > 1:
        confidence = confidence / 100

    return max(0.0, min(1.0, confidence))


def claim_confidence_status(confidence):
    confidence = normalize_confidence_score(confidence)
    if confidence is None:
        return None

    if confidence >= 0.90:
        return "AUTO_APPROVED"
    if confidence >= 0.70:
        return "VALIDATION_REQUIRED"
    return "HUMAN_REVIEW_REQUIRED"

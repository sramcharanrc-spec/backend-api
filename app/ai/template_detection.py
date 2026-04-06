def detect_template_rule_based(extracted: dict):

    text = " ".join([str(v) for v in extracted.values() if isinstance(v, str)]).upper()

    cms_score = 0
    ub_score = 0

    # 🔹 CMS signals (text-based)
    if "CMS-1500" in text:
        cms_score += 30

    if "CPT" in text:
        cms_score += 15

    # 🔹 NEW: field-based detection
    if extracted.get("Code") or extracted.get("Another Code"):
        cms_score += 20

    if extracted.get("Provider"):
        cms_score += 10

    if extracted.get("Insurance"):
        cms_score += 10

    if extracted.get("Total"):
        cms_score += 10

    # -------------------------
    # DECISION
    # -------------------------
    if cms_score >= 30:
        template = "CMS-1500"
        confidence = cms_score / 100
    else:
        template = "Unknown"
        confidence = cms_score / 100

    # -------------------------
    # 🚦 STATUS FIX (IMPORTANT)
    # -------------------------
    if confidence < 0.3:
        status = "needs_review"
    else:
        status = "processing"

    return {
        "template_name": template,
        "confidence": round(confidence, 2),
        "status": status,
        "scores": {
            "cms": cms_score,
            "ub": ub_score
        }
    }
class TemplateResult(dict):
    """Dict result that also supports legacy async callers using await."""

    def __await__(self):
        async def _result():
            return self

        return _result().__await__()


def detect_template(data):
    """
    Hybrid rule-based template detection with explainability
    Supports CMS-1500 + UB-04
    """

    if not isinstance(data, dict):
        data = {"raw": data}

    text = " ".join(str(v) for v in data.values() if isinstance(v, str)).upper()

    cms_score = 0
    ub_score = 0
    signals = []

    # -------------------------
    # 🔹 CMS-1500 Signals
    # -------------------------
    if "CMS-1500" in text:
        cms_score += 40
        signals.append("CMS keyword")

    if "CPT" in text:
        cms_score += 20
        signals.append("CPT codes")

    if any(k in data for k in ["provider_npi", "npi", "Provider"]):
        cms_score += 10
        signals.append("Provider info")

    if any(k in data for k in ["diagnosis", "ICD", "icd_codes"]):
        cms_score += 10
        signals.append("Diagnosis codes")

    if any(k in data for k in ["Total", "total_charge", "amount"]):
        cms_score += 10
        signals.append("Charge info")

    # -------------------------
    # 🔹 UB-04 Signals (Hospital forms)
    # -------------------------
    if "UB-04" in text:
        ub_score += 40
        signals.append("UB keyword")

    if "REVENUE CODE" in text:
        ub_score += 25
        signals.append("Revenue codes")

    if "TYPE OF BILL" in text:
        ub_score += 20
        signals.append("Type of bill")

    if "ADMISSION DATE" in text:
        ub_score += 15
        signals.append("Admission info")

    # -------------------------
    # 🔹 DECISION LOGIC
    # -------------------------
    if cms_score > ub_score and cms_score >= 30:
        template = "CMS-1500"
        confidence = cms_score / 100
    elif ub_score > cms_score and ub_score >= 30:
        template = "UB-04"
        confidence = ub_score / 100
    else:
        template = "Unknown"
        confidence = max(cms_score, ub_score) / 100

    # -------------------------
    # 🔹 STATUS
    # -------------------------
    if confidence >= 0.7:
        status = "high_confidence"
    elif confidence >= 0.4:
        status = "medium_confidence"
    else:
        status = "needs_review"

    extraction_quality = "high" if confidence >= 0.7 else "medium" if confidence >= 0.4 else "low"

    return TemplateResult({
        "template": template,
        "template_name": template,
        "confidence": round(confidence, 2),
        "confidence_score": round(confidence, 2),
        "extraction_quality": extraction_quality,
        "fallback_to_hitl": confidence < 0.4,
        "status": status,
        "scores": {
            "cms": cms_score,
            "ub": ub_score
        },
        "signals": signals  # 🔥 explainability
    })


def detect_template_rule_based(data):
    """Backward-compatible name used by older processor imports."""
    return detect_template(data)

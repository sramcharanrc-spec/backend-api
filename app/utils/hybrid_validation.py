

def _percent(value, default=0):
    try:
        number = float(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    return number * 100 if 0 < number <= 1 else number


def _has_any(container, *keys):
    return any(container.get(key) for key in keys)


def weighted_validation(claim):
    """
    Weighted validation score:
    required fields 25%, OCR confidence 15%, CPT/ICD 20%,
    coverage criteria 15%, payer rules 15%, compliance 10%.
    """
    patient = claim.get("patient") or {}
    provider = claim.get("provider") or {}
    payer = claim.get("payer") or {}
    extraction = claim.get("extraction") or {}
    compliance = claim.get("compliance") or claim.get("compliance_results") or {}
    payer_rules = claim.get("payer_rules") or claim.get("payer_rule_findings") or {}
    coverage = claim.get("coverage") or claim.get("coverage_criteria") or {}
    services = claim.get("services") or []
    cpt_codes = claim.get("cpt_codes") or [svc.get("cpt") for svc in services if svc.get("cpt")]
    icd_codes = claim.get("icd_codes") or claim.get("diagnosis_codes") or []

    required_values = [
        patient.get("name"),
        patient.get("dob"),
        provider.get("npi"),
        payer.get("name"),
        services,
        claim.get("total_charge"),
    ]
    required_score = sum(1 for value in required_values if value) / len(required_values)

    ocr_default = 100 if not extraction and claim.get("confidence") is None else 0
    ocr_score = _percent(
        extraction.get("ocr_quality")
        or extraction.get("extraction_confidence")
        or claim.get("confidence"),
        ocr_default,
    ) / 100

    code_score = (1 if cpt_codes else 0) * 0.5 + (1 if icd_codes else 0) * 0.5

    coverage_failed = str(coverage.get("status", "")).upper() in {"FAILED", "FAIL", "DENIED", "NOT_COVERED"}
    coverage_issues = coverage.get("issues") or coverage.get("gaps") or []
    coverage_score = 0 if coverage_failed else 0.5 if coverage_issues else 1

    payer_findings = payer_rules if isinstance(payer_rules, list) else payer_rules.get("findings") or payer_rules.get("issues") or []
    payer_score = 0.5 if payer_findings else 1 if payer.get("name") and payer.get("name") != "UNKNOWN_PAYER" else 0

    compliance_failed = str(compliance.get("status", "")).upper() in {"FAILED", "FAIL", "NON_COMPLIANT", "BLOCKED", "HITL_REQUIRED"}
    compliance_issues = compliance.get("issues") or compliance.get("warnings") or []
    compliance_score = 0 if compliance_failed else 0.5 if compliance_issues or claim.get("hitl_required") else 1

    component_scores = {
        "required_fields": required_score,
        "ocr_confidence": ocr_score,
        "cpt_icd": code_score,
        "coverage_criteria": coverage_score,
        "payer_rules": payer_score,
        "compliance": compliance_score,
    }
    weights = {
        "required_fields": 0.25,
        "ocr_confidence": 0.15,
        "cpt_icd": 0.20,
        "coverage_criteria": 0.15,
        "payer_rules": 0.15,
        "compliance": 0.10,
    }
    score = sum(component_scores[key] * weight for key, weight in weights.items())

    return {
        "score": round(score, 2),
        "is_valid": score >= 0.75 and not compliance_failed,
        "components": {key: round(value, 2) for key, value in component_scores.items()},
        "weights": weights,
    }

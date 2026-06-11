from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict


def normalize_claim_ai(claim: Dict[str, Any]) -> Dict[str, Any]:
    """AI-assisted DEV normalizer using deterministic healthcare heuristics."""
    normalized = deepcopy(claim or {})
    normalized.setdefault("patient", {})
    normalized.setdefault("provider", {})
    normalized.setdefault("payer", {})
    normalized.setdefault("services", [])

    for key in ["npi", "tax_id"]:
        if normalized["provider"].get(key):
            normalized["provider"][key] = _digits(normalized["provider"][key])

    if normalized["payer"].get("name"):
        normalized["payer"]["name"] = _clean_payer(normalized["payer"]["name"])

    for service in normalized["services"]:
        code = service.get("cpt") or service.get("cpt_code")
        if code:
            repaired = _repair_ocr_digits(str(code))
            service["cpt"] = repaired
            service["cpt_code"] = repaired
        service["units"] = int(service.get("units") or 1)
        service["charge"] = float(service.get("charge") or 100)
        if not service.get("date_of_service") and normalized.get("service_date"):
            service["date_of_service"] = normalized["service_date"]

    if not normalized.get("icd_codes") and normalized.get("diagnosis_codes"):
        normalized["icd_codes"] = normalized["diagnosis_codes"]
    if not normalized.get("diagnosis_codes") and normalized.get("icd_codes"):
        normalized["diagnosis_codes"] = normalized["icd_codes"]
    if not normalized.get("icd_codes"):
        normalized["icd_codes"] = ["Z00.00"]
        normalized["diagnosis_codes"] = ["Z00.00"]

    normalized["cpt_codes"] = list({
        service.get("cpt") for service in normalized["services"] if service.get("cpt")
    })
    normalized["total_charge"] = float(normalized.get("total_charge") or sum(
        float(service.get("charge") or 0) * int(service.get("units") or 1)
        for service in normalized["services"]
    ))
    normalized["normalization"] = {
        "engine": "ai_normalizer_heuristic",
        "ocr_repairs": ["O->0", "I->1", "S->5", "B->8"],
    }
    return normalized


def _repair_ocr_digits(value: str) -> str:
    return value.upper().translate(str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8"}))


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _clean_payer(value: str) -> str:
    payer = re.sub(r"\s+", " ", str(value).strip())
    replacements = {
        "BC BS": "BCBS",
        "BLUE CROSS BLUE SHIELD": "BCBS",
        "AETNA HEALTH": "AETNA",
        "UNITED HEALTHCARE": "UNITEDHEALTHCARE",
    }
    return replacements.get(payer.upper(), payer)

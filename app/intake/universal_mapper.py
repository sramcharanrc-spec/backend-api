from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from app.intake.ai_normalizer import normalize_claim_ai
from app.intake.form_classifier import classify_form
from app.intake.form_normalizer import fix_split_dates
from app.intake.service_line_parser import parse_service_lines


def map_universal_claim(textract_or_parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map arbitrary Textract OCR output into the platform claim schema.

    Used by PDF/image processors after Textract parsing.
    Produces downstream fields:
    patient, provider, payer, services, icd_codes, cpt_codes, total_charge,
    extraction confidence, and form detection.
    """

    start_time = time.time()

    print("\n" + "-" * 80)
    print("🧩 [UniversalMapper] STARTED")

    textract_or_parsed = textract_or_parsed or {}

    form = classify_form(textract_or_parsed)

    fields = (
        textract_or_parsed.get("fields", {})
        if isinstance(textract_or_parsed, dict)
        else {}
    )

    lines = _lines(textract_or_parsed)
    text = "\n".join(lines)

    print(f"📄 Form type: {form.get('form_type')}")
    print(f"📊 Form confidence: {form.get('confidence')}")
    print(f"🧾 Lines: {len(lines)}")
    print(f"📋 Fields: {len(fields)}")

    # ---------------------------------------------------
    # Service line extraction
    # ---------------------------------------------------
    print("➡️ [1] Parsing service lines...")

    services = parse_service_lines(textract_or_parsed)
    services = normalize_services(services)
    services = filter_valid_service_lines(services)

    fallback_date = _fallback_service_date(fields, lines)

    if fallback_date:
        for service in services:
            service["service_date"] = fallback_date
            service["date_of_service"] = fallback_date
            service["date"] = fallback_date
            service["dos"] = fallback_date

    print(f"✅ Services parsed: {len(services)}")

    # ---------------------------------------------------
    # Patient extraction
    # ---------------------------------------------------
    print("➡️ [2] Extracting patient information...")

    patient = {
        "name": (
            _field(fields, ["patient name", "name", "insured name"])
            or _regex(
                text,
                r"(?:PATIENT|INSURED)\s*NAME[:\s]+([A-Z ,.'-]{3,80})",
            )
        ),
        "dob": fix_split_dates(
            _field(fields, ["date of birth", "dob", "birth date", "birth"])
            or _regex(
                text,
                r"\b(?:DOB|BIRTH DATE|BIRTH)\s*[:#]?\s*(\d{1,2}(?:[/-]|\s+)\d{1,2}(?:[/-]|\s+)\d{2,4})",
            )
        ),
        "member_id": (
            _field(fields, ["member id", "policy id", "policy", "insured id"])
            or _regex(
                text,
                r"\b(?:MEMBER|POLICY|INSURED)\s*(?:ID|NO|#)?\s*[:#]?\s*([A-Z0-9-]{4,30})",
            )
        ),
    }

    # Remove DOB-as-service-date mistakes after patient DOB is known.
    services = clean_service_dates(services, claim={"patient": patient})

    # ---------------------------------------------------
    # Provider extraction
    # ---------------------------------------------------
    print("➡️ [3] Extracting provider information...")

    raw_npi = (
        _field(fields, ["npi", "provider npi", "rendering npi"])
        or _regex(text, r"\bNPI\s*[:#]?\s*([0-9OISB]{10})")
    )

    provider = {
        "name": _field(
            fields,
            ["provider name", "billing provider", "rendering provider"],
        ),
        "npi": normalize_npi(raw_npi),
    }

    # ---------------------------------------------------
    # Payer extraction
    # ---------------------------------------------------
    print("➡️ [4] Extracting payer information...")

    payer = {
        "name": (
            _field(fields, ["payer", "insurance", "plan name"])
            or _regex(
                text,
                r"\b(?:PAYER|INSURANCE|PLAN)\s*[:#]?\s*([A-Z0-9 &.-]{3,60})",
            )
        ),
    }

    # ---------------------------------------------------
    # Codes / totals
    # ---------------------------------------------------
    print("➡️ [5] Extracting ICD/CPT codes and total charge...")

    diagnosis_codes = _diagnosis_codes(text)
    cpt_codes = _cpt_codes(text, services)
    total_charge = _total_charge(text, services)

    print(f"✅ ICD codes: {diagnosis_codes}")
    print(f"✅ CPT codes: {cpt_codes}")
    print(f"✅ Total charge: {total_charge}")

    # ---------------------------------------------------
    # Build and normalize claim
    # ---------------------------------------------------
    print("➡️ [6] Building normalized claim...")

    claim = normalize_claim_ai(
        {
            "patient": {
                key: value
                for key, value in patient.items()
                if value
            },
            "insurance": {
                "member_id": patient.get("member_id")
            },
            "payer": {
                key: value
                for key, value in payer.items()
                if value
            },
            "diagnosis_codes": diagnosis_codes,
            "icd_codes": diagnosis_codes,
            "cpt_codes": cpt_codes,
            "services": services,
            "provider": {
                key: value
                for key, value in provider.items()
                if value
            },
            "totals": {
                "charge": total_charge
            },
            "total_charge": total_charge,
            "claim_type": form.get("form_type"),
            "form_type": form.get("form_type"),
            "document_type": form.get("document_type") or form.get("form_type"),
        }
    )

    # Guarantee downstream-compatible fields even if normalize_claim_ai drops them.
    claim.setdefault("patient", {})
    claim.setdefault("provider", {})
    claim.setdefault("payer", {})
    claim.setdefault("insurance", {})
    claim.setdefault("services", services)
    claim.setdefault("icd_codes", diagnosis_codes)
    claim.setdefault("diagnosis_codes", diagnosis_codes)
    claim.setdefault("cpt_codes", cpt_codes)
    claim.setdefault("total_charge", total_charge)
    claim.setdefault("claim_type", form.get("form_type"))
    claim.setdefault("form_type", form.get("form_type"))
    claim.setdefault("document_type", form.get("document_type") or form.get("form_type"))

    confidence = score_extraction(claim, textract_or_parsed, form)

    duration_seconds = round(time.time() - start_time, 2)

    confidence["duration_seconds"] = duration_seconds
    confidence["processor"] = "universal_mapper"

    claim["extraction"] = confidence
    claim["field_confidence"] = _field_confidence(claim, confidence, form)
    claim["form_detection"] = form

    # Ratio versions for agents that prefer 0-1 values.
    claim["extraction_confidence"] = confidence["extraction_confidence"]
    claim["extraction_confidence_ratio"] = round(
        confidence["extraction_confidence"] / 100,
        2,
    )

    claim["validation_score"] = confidence["validation_score"]
    claim["validation_score_ratio"] = round(
        confidence["validation_score"] / 100,
        2,
    )

    claim["risk_score"] = confidence["risk_score"]
    claim["risk_score_ratio"] = round(
        confidence["risk_score"] / 100,
        2,
    )

    print("✅ [UniversalMapper] COMPLETED")
    print(f"📊 Extraction confidence: {confidence['extraction_confidence']}%")
    print(f"📊 Validation score: {confidence['validation_score']}%")
    print(f"📊 Risk score: {confidence['risk_score']}%")
    print(f"⏱️ Mapper duration: {duration_seconds}s")
    print("-" * 80 + "\n")

    return claim


def _fallback_service_date(fields, lines):
    """
    Extract service date only from explicit service-date labels.
    Do not use the first random date in the document, because that can pick
    patient DOB instead of Date Of Service.
    """

    fields = fields or {}

    candidates = [
        fields.get("Date Of Service"),
        fields.get("Date of Service"),
        fields.get("DATE OF SERVICE"),
        fields.get("Service Date"),
        fields.get("SERVICE DATE"),
        fields.get("DOS"),
        fields.get("Dos"),
        fields.get("From Date"),
        fields.get("To Date"),
        fields.get("Service From"),
        fields.get("Service To"),
    ]

    for value in candidates:
        if value:
            return str(value).strip()

    text = " ".join(str(line) for line in (lines or []))

    match = re.search(
        r"(?:date\s*of\s*service|service\s*date|dos)\s*[:#-]?\s*"
        r"([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return ""


def score_extraction(
    claim: Dict[str, Any],
    textract_or_parsed: Dict[str, Any],
    form: Dict[str, Any],
) -> Dict[str, Any]:
    services = claim.get("services") or []

    required = [
        claim.get("patient", {}).get("name"),
        claim.get("patient", {}).get("dob"),
        claim.get("provider", {}).get("npi"),
        claim.get("payer", {}).get("name"),
        services,
        claim.get("total_charge"),
    ]

    field_completion = round(
        sum(1 for value in required if value) / len(required) * 100
    )

    service_confidence = (
        round(
            min(
                100,
                len(services) * 65
                + sum(
                    safe_float(service.get("confidence"), 0.75)
                    for service in services
                )
                * 25
                / max(len(services), 1),
            )
        )
        if services
        else 0
    )

    ocr_quality = _ocr_quality(textract_or_parsed)

    form_confidence = safe_float(form.get("confidence"), 0.75)
    if form_confidence <= 1:
        form_confidence = form_confidence * 100

    extraction_confidence = round(
        (field_completion * 0.35)
        + (service_confidence * 0.35)
        + (ocr_quality * 0.2)
        + (form_confidence * 0.1)
    )

    validation_score = max(
        0,
        min(
            100,
            round(extraction_confidence - _risk_penalty(claim)),
        ),
    )

    risk_score = max(0, min(100, 100 - validation_score))

    return {
        "form_type": form.get("form_type"),
        "layout_type": form.get("layout_version"),
        "ocr_quality": ocr_quality,
        "extraction_confidence": extraction_confidence,
        "extraction_confidence_ratio": round(extraction_confidence / 100, 2),
        "field_completion": field_completion,
        "service_confidence": service_confidence,
        "service_extraction": service_confidence,
        "validation_score": validation_score,
        "validation_score_ratio": round(validation_score / 100, 2),
        "risk_score": risk_score,
        "risk_score_ratio": round(risk_score / 100, 2),
        "low_confidence": extraction_confidence < 75,
    }


def _lines(textract_or_parsed: Dict[str, Any]) -> List[str]:
    if not isinstance(textract_or_parsed, dict):
        return []

    if textract_or_parsed.get("lines"):
        return [
            str(line)
            for line in textract_or_parsed["lines"]
        ]

    return [
        str(block.get("Text", ""))
        for block in textract_or_parsed.get("Blocks", [])
        if block.get("BlockType") == "LINE" and block.get("Text")
    ]


def _field(fields: Dict[str, Any], names: List[str]) -> str:
    normalized = {
        str(key).lower().strip(): value
        for key, value in (fields or {}).items()
    }

    for name in names:
        for key, value in normalized.items():
            if name in key and value:
                return str(value).strip()

    return ""


def _regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip(" :#\n\t") if match else ""


def _diagnosis_codes(text: str) -> List[str]:
    return list(
        dict.fromkeys(
            re.findall(
                r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b",
                text.upper(),
            )
        )
    )[:12]


def _cpt_codes(text: str, services: List[Dict[str, Any]]) -> List[str]:
    codes = []

    for service in services or []:
        if not isinstance(service, dict):
            continue

        code = (
            service.get("cpt")
            or service.get("cpt_code")
            or service.get("procedure_code")
            or service.get("hcpcs")
        )

        if code:
            code = str(code).strip()
            if code.isdigit() and len(code) == 5:
                codes.append(code)

    return list(dict.fromkeys(codes))[:20]


def _total_charge(text: str, services: List[Dict[str, Any]]) -> float:
    valid_services = filter_valid_service_lines(services)

    calculated_total = sum(
        safe_float(service.get("charge") or service.get("charge_amount"))
        * safe_int(service.get("units"), 1)
        for service in valid_services
    )

    if calculated_total > 0:
        return round(calculated_total, 2)

    total_match = re.search(
        r"\bTOTAL\s*(?:CHARGE|AMOUNT|DUE)?\s*[:#]?\s*\$?([\d,]+(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )

    if total_match:
        return safe_float(total_match.group(1).replace(",", ""))

    return 0.0


def _ocr_quality(textract_or_parsed: Dict[str, Any]) -> int:
    if not isinstance(textract_or_parsed, dict):
        return 75

    metadata = textract_or_parsed.get("metadata") or {}

    confidence_value = (
        metadata.get("average_confidence")
        or metadata.get("avg_confidence")
        or metadata.get("confidence")
    )

    if confidence_value:
        value = safe_float(confidence_value, 75)
        return round(value * 100) if value <= 1 else round(value)

    confidences = [
        float(block.get("Confidence", 0))
        for block in textract_or_parsed.get("Blocks", [])
        if block.get("BlockType") in {"WORD", "LINE"}
        and block.get("Confidence") is not None
    ]

    return round(sum(confidences) / len(confidences)) if confidences else 75


def _risk_penalty(claim: Dict[str, Any]) -> int:
    penalty = 0

    if not claim.get("services"):
        penalty += 35

    if not claim.get("provider", {}).get("npi"):
        penalty += 10

    if not claim.get("icd_codes"):
        penalty += 10

    if not claim.get("cpt_codes"):
        penalty += 10

    return penalty


def _field_confidence(
    claim: Dict[str, Any],
    confidence: Dict[str, Any],
    form: Dict[str, Any],
) -> List[Dict[str, Any]]:
    base = confidence.get("extraction_confidence", 70) / 100

    fields = [
        ("patient.name", claim.get("patient", {}).get("name")),
        ("patient.dob", claim.get("patient", {}).get("dob")),
        ("provider.npi", claim.get("provider", {}).get("npi")),
        ("payer.name", claim.get("payer", {}).get("name")),
        ("total_charge", claim.get("total_charge")),
    ]

    for index, service in enumerate(claim.get("services", [])):
        fields.extend(
            [
                (f"services[{index}].cpt_code", service.get("cpt")),
                (f"services[{index}].charge", service.get("charge")),
                (f"services[{index}].units", service.get("units")),
            ]
        )

    return [
        {
            "field": field,
            "value": "" if value is None else str(value),
            "confidence": round(
                min(
                    0.99,
                    max(
                        0.35,
                        base if value else base - 0.28,
                    ),
                ),
                2,
            ),
            "form_type": form.get("form_type"),
        }
        for field, value in fields
    ]


def normalize_services(services):
    normalized = []

    for service in services or []:
        if not isinstance(service, dict):
            continue

        cpt = (
            service.get("cpt")
            or service.get("cpt_code")
            or service.get("procedure_code")
            or service.get("hcpcs")
        )

        charge = safe_float(
            service.get("charge")
            or service.get("charge_amount")
            or service.get("amount")
        )

        units = safe_int(service.get("units"))

        normalized.append(
            {
                **service,
                "cpt": str(cpt).strip() if cpt else None,
                "cpt_code": str(cpt).strip() if cpt else None,
                "charge": charge,
                "charge_amount": charge,
                "units": units,
            }
        )

    return normalized


def filter_valid_service_lines(services):
    cleaned = []

    invalid_markers = [
        "compliance failed rule",
        "failed rule",
        "warning rule",
        "denial risk",
        "expected output",
        "authorization requirement",
        "clearinghouse",
        "sample",
        "test data",
        "payer message",
        "suggested correction",
    ]

    for service in services or []:
        if not isinstance(service, dict):
            continue

        cpt = str(
            service.get("cpt")
            or service.get("cpt_code")
            or service.get("procedure_code")
            or service.get("hcpcs")
            or ""
        ).strip()

        description = str(service.get("description") or "").lower()

        charge = safe_float(
            service.get("charge")
            or service.get("charge_amount")
            or service.get("amount")
            or 0
        )

        if not cpt.isdigit() or len(cpt) != 5:
            continue

        if any(marker in description for marker in invalid_markers):
            continue

        if charge <= 0 or charge > 10000:
            continue

        cleaned.append(
            {
                **service,
                "cpt": cpt,
                "cpt_code": cpt,
                "charge": charge,
                "charge_amount": charge,
                "units": safe_int(service.get("units"), 1),
            }
        )

    return cleaned


def clean_service_dates(services, claim=None):
    claim = claim or {}
    patient_dob = str((claim.get("patient") or {}).get("dob") or "").strip()

    for service in services or []:
        service_date = str(
            service.get("service_date")
            or service.get("date_of_service")
            or service.get("dos")
            or ""
        ).strip()

        if patient_dob and service_date == patient_dob:
            service["service_date"] = None
            service["date_of_service"] = None
            service["date"] = None
            service["dos"] = None

    return services


def normalize_npi(value):
    if not value:
        return None

    text = str(value).upper().strip()

    replacements = {
        "O": "0",
        "I": "1",
        "S": "5",
        "B": "8",
    }

    for bad, good in replacements.items():
        text = text.replace(bad, good)

    digits = re.sub(r"\D", "", text)

    return digits if len(digits) == 10 else None


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()

        return float(value or default)

    except (TypeError, ValueError):
        return default


def safe_int(value, default=1):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default
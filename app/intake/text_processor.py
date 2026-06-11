import re
import tempfile
from typing import Any, Dict

from app.intake.s3_service import download_file
from app.utils.id_generator import generate_claim_id
from app.websocket.manager import manager


def _safe_float(value):
    try:
        if value is None:
            return 0.0

        value = (
            str(value)
            .replace("$", "")
            .replace(",", "")
            .replace("USD", "")
            .strip()
        )

        return float(value or 0)

    except (TypeError, ValueError):
        return 0.0


def _safe_int(value, default=1):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _extract(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else default


def _extract_line_value(label: str, text: str, default: str = "") -> str:
    """
    Extracts only the value on the same line as the label.

    Important:
    Do not use \\s* after ':' because \\s can consume newlines.
    For example:

        NPI:
        Tax ID: 223344556

    should return empty string for NPI, not "Tax ID: 223344556".
    """
    pattern = rf"^{re.escape(label)}[ \t]*:[ \t]*([^\n\r]*)"
    return _extract(pattern, text, default)


def _missing_fields(claim: Dict[str, Any]) -> list[str]:
    missing = []

    if not claim.get("patient", {}).get("name"):
        missing.append("patient.name")

    if not claim.get("patient", {}).get("dob"):
        missing.append("patient.dob")

    if not claim.get("insurance", {}).get("member_id"):
        missing.append("insurance.member_id")

    if not claim.get("payer", {}).get("name"):
        missing.append("payer.name")

    if not claim.get("provider", {}).get("npi"):
        missing.append("provider.npi")

    if not claim.get("services"):
        missing.append("services")

    if not claim.get("icd_codes"):
        missing.append("icd_codes")

    if not claim.get("cpt_codes"):
        missing.append("cpt_codes")

    return missing


async def process_text(bucket: str, key: str, claim_id: str = "") -> Dict[str, Any]:
    claim_id = claim_id or generate_claim_id()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        local_path = tmp.name

    download_file(bucket, key, local_path)

    with open(local_path, "r", encoding="utf-8", errors="ignore") as uploaded_file:
        text = uploaded_file.read()

    patient_name = _extract_line_value("Patient Name", text)
    dob = _extract_line_value("DOB", text)
    gender = _extract_line_value("Gender", text)
    member_id = _extract_line_value("Member ID", text)
    payer_name = _extract_line_value("Insurance Payer", text)
    policy_number = _extract_line_value("Policy Number", text)
    group_number = _extract_line_value("Group Number", text)
    provider_name = _extract_line_value("Rendering Provider", text)
    facility = _extract_line_value("Facility", text)
    provider_npi = _extract_line_value("NPI", text)
    if ":" in provider_npi:
        provider_npi = ""

    if provider_npi and not provider_npi.isdigit():
        provider_npi = ""
    provider_tax_id = _extract_line_value("Tax ID", text)
    icd_primary = _extract_line_value("ICD-10 Primary", text)
    icd_secondary = _extract_line_value("ICD-10 Secondary", text)
    cpt = _extract_line_value("CPT", text)
    modifier = _extract_line_value("Modifier", text)
    units = _extract_line_value("Units", text)
    service_date = _extract_line_value("Date Of Service", text)
    pos = _extract_line_value("Place Of Service", text)
    prior_auth = _extract_line_value("Prior Authorization", text)
    charge = _extract_line_value("Charge Amount", text)
    patient_address = _extract_line_value("Patient Address", text)
    phone = _extract_line_value("Phone", text)

    icd_codes = [code for code in [icd_primary, icd_secondary] if code]
    cpt_codes = [cpt] if cpt else []

    charge_amount = _safe_float(charge)
    service_units = _safe_int(units, default=1)

    services = []
    if cpt:
        services.append(
            {
                "date_of_service": service_date,
                "service_date": service_date,
                "dos": service_date,
                "cpt": cpt,
                "cpt_code": cpt,
                "modifier": modifier,
                "modifiers": [modifier] if modifier else [],
                "units": service_units,
                "charge": charge_amount,
                "charge_amount": charge_amount,
                "place_of_service": pos,
                "pos": pos,
                "prior_authorization": prior_auth,
                "source": "text_processor",
            }
        )

    source_file = {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "file_type": "txt",
    }

    claim = {
        "claim_id": claim_id,
        "id": claim_id,
        "source_file": source_file,
        "patient": {
            "name": patient_name,
            "dob": dob,
            "gender": gender,
            "member_id": member_id,
            "address": patient_address,
            "phone": phone,
        },
        "insurance": {
            "member_id": member_id,
            "payer": payer_name,
            "policy_number": policy_number,
            "group_number": group_number,
        },
        "payer": {
            "name": payer_name,
        },
        "provider": {
            "name": provider_name,
            "npi": provider_npi,
            "tax_id": provider_tax_id,
        },
        "facility": facility,
        "diagnosis_codes": icd_codes,
        "icd_codes": icd_codes,
        "cpt_codes": cpt_codes,
        "services": services,
        "total_charge": charge_amount,
        "form_type": "CMS1500",
        "document_type": "CMS1500",
        "claim_type": "CMS1500",
        "source": "TEXT",
        "file_name": key,
        "filename": key,
        "confidence": 1.0,
        "extraction_confidence": 1.0,
        "confidence_status": "AUTO_APPROVED",
        "requires_human_review": False,
        "missing_fields": [],
        "intake": {
            "processor": "text_processor",
            "document_type": "CMS1500",
            "service_count": len(services),
            "confidence": 1.0,
        },
        "extraction": {
            "processor": "text_processor",
            "raw_text_length": len(text),
            "extraction_confidence": 1.0,
            "requires_human_review": False,
            "missing_fields": [],
        },
    }

    missing = _missing_fields(claim)
    claim["missing_fields"] = missing
    claim["extraction"]["missing_fields"] = missing
    claim["extraction"]["requires_human_review"] = bool(missing)

    if missing:
        claim["requires_human_review"] = True
        claim["status"] = "HUMAN_REVIEW_REQUIRED"
        claim["review_status"] = "NEEDS_REVIEW"
        claim["queue_state"] = "HUMAN_REVIEW"
        claim["current_stage"] = "HUMAN_REVIEW"
        claim["active_step"] = "human_review_required"
        claim["current_agent"] = "HUMAN_REVIEW"
        claim["reason"] = f"Missing required fields: {', '.join(missing)}"
        claim["confidence_status"] = "NEEDS_REVIEW"
    else:
        claim["status"] = "AUTO_APPROVED"

    await manager.broadcast(
        {
            "event": "extraction_completed",
            "type": "extraction_completed",
            "claim_id": claim_id,
            "processor": "text_processor",
            "form_type": "CMS1500",
            "document_type": "CMS1500",
            "missing_fields": missing,
            "requires_human_review": bool(missing),
            "source_file": source_file,
        }
    )

    return claim
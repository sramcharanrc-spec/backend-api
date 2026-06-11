# import math
# import uuid
# from datetime import datetime


# def generate_claim_id() -> str:
#     return f"CLM-{uuid.uuid4().hex[:10]}"


# def _is_blank(value) -> bool:
#     if value is None:
#         return True
#     if isinstance(value, float) and math.isnan(value):
#         return True
#     return str(value).strip() == ""


# def _get(row: dict, *keys, default=None):
#     normalized = {str(key).strip().lower(): value for key, value in row.items()}

#     for key in keys:
#         if key in row and not _is_blank(row[key]):
#             return row[key]

#         value = normalized.get(str(key).strip().lower())
#         if not _is_blank(value):
#             return value

#     return default


# def _str(row: dict, *keys, default=""):
#     value = _get(row, *keys, default=default)
#     if _is_blank(value):
#         return default
#     return str(value).strip()


# def _float(row: dict, *keys, default=0.0):
#     value = _get(row, *keys, default=default)
#     try:
#         return float(str(value).replace(",", "").replace("$", ""))
#     except (TypeError, ValueError):
#         return default


# def _int(row: dict, *keys, default=1):
#     value = _get(row, *keys, default=default)
#     try:
#         return int(float(str(value).replace(",", "")))
#     except (TypeError, ValueError):
#         return default


# def _date_string(row: dict, *keys, default="1990-01-01"):
#     value = _get(row, *keys)
#     if _is_blank(value):
#         return default
#     if hasattr(value, "date"):
#         return value.date().isoformat()
#     return str(value).strip()


# def _split_codes(value):
#     if _is_blank(value):
#         return []
#     if isinstance(value, list):
#         return [str(item).strip() for item in value if not _is_blank(item)]
#     return [
#         code.strip()
#         for code in str(value).replace("|", ",").replace(";", ",").split(",")
#         if code.strip()
#     ]


# def _normalize_claim_type(value, encounter_type="outpatient"):
#     raw = str(value or "").strip().upper().replace("-", "").replace("_", "").replace(" ", "")
#     if raw in {"CMS1500", "CMS", "PROFESSIONAL", "OUTPATIENT"}:
#         return "CMS1500"
#     if raw in {"UB04", "UB", "INSTITUTIONAL", "INPATIENT"}:
#         return "UB04"
#     if raw in {"BOTH", "CMS1500UB04", "UB04CMS1500"}:
#         return "BOTH"
#     return "UB04" if str(encounter_type).lower() == "inpatient" else "CMS1500"


# def _build_services(row: dict) -> list[dict]:
#     services = []

#     for index in range(1, 7):
#         cpt = _str(
#             row,
#             f"CPT{index}",
#             f"CPT {index}",
#             f"Procedure Code {index}",
#             f"HCPCS{index}",
#             default="",
#         )
#         if not cpt and index == 1:
#             cpt = _str(row, "CPT", "Procedure Code", "HCPCS", "Service Code", default="")

#         if not cpt:
#             continue

#         charge = _float(row, f"Charge{index}", f"Charge {index}", f"Amount{index}", "Charge", "Amount", default=0.0)
#         units = _int(row, f"Units{index}", f"Units {index}", "Units", default=1)
#         diagnosis_pointer = _str(row, f"Diagnosis Pointer {index}", "Diagnosis Pointer", default="1")

#         services.append({
#             "cpt": cpt,
#             "charge": charge,
#             "units": units,
#             "diagnosis_pointer": diagnosis_pointer,
#         })

#     return services


# def transform_excel_row_to_claim(row: dict) -> dict:
#     services = _build_services(row)
#     cpt_codes = [service["cpt"] for service in services]
#     icd_codes = _split_codes(_get(row, "ICD", "ICD10", "Diagnosis", "Diagnosis Code", "diagnosis1"))
#     total_charge = _float(row, "Total Charge", "Charge", "Amount", "Billed Amount", default=0.0)

#     if not total_charge:
#         total_charge = sum(service["charge"] * service["units"] for service in services)

#     claim_id = _str(row, "claim_id", "Claim ID", "ClaimID", default="") or generate_claim_id()
#     encounter_type = _str(row, "encounter_type", "Encounter Type", "Claim Type", default="outpatient").lower()
#     if encounter_type not in {"outpatient", "inpatient"}:
#         encounter_type = "inpatient" if encounter_type in {"ub04", "ub-04", "institutional"} else "outpatient"
#     claim_type = _normalize_claim_type(
#         _str(row, "claim_type", "Claim Type", "Form Type", "Form", "CMS Form", default=""),
#         encounter_type,
#     )

#     patient_name = _str(row, "Patient Name", "Patient", "Name", "pt_name", default="Unknown")
#     provider_npi = _str(row, "NPI", "Provider NPI", "billing_provider_npi", default="UNKNOWN")
#     payer_name = _str(row, "Payer", "Insurance", "Insurance Name", "insurance_name", default="UNKNOWN")
#     member_id = _str(row, "Insurance ID", "Member ID", "Policy ID", "Policy", default="UNKNOWN")

#     claim = {
#         "claim_id": claim_id,
#         "submission_id": _str(row, "submission_id", "Submission ID", default=claim_id),
#         "claim_type": claim_type,
#         "encounter_type": encounter_type,
#         "patient_name": patient_name,
#         "pt_name": patient_name,
#         "dob": _date_string(row, "DOB", "Date of Birth", "patient_dob"),
#         "patient": {
#             "name": patient_name,
#             "dob": _date_string(row, "DOB", "Date of Birth", "patient_dob"),
#         },
#         "provider": {
#             "npi": provider_npi,
#             "name": _str(row, "Provider", "Provider Name", default=""),
#         },
#         "payer": {
#             "name": payer_name,
#         },
#         "insurance": {
#             "member_id": member_id,
#             "payer": payer_name,
#         },
#         "billing_provider_npi": provider_npi,
#         "insurance_name": payer_name,
#         "insurance_id": member_id,
#         "diagnosis1": icd_codes[0] if icd_codes else _str(row, "diagnosis1", default=""),
#         "icd_codes": icd_codes,
#         "cpt_codes": cpt_codes,
#         "cpt1": cpt_codes[0] if cpt_codes else "",
#         "services": services,
#         "total_charge": total_charge,
#         "source": "EXCEL",
#         "metadata": {
#             "claim_type": claim_type,
#             "source_type": "EXCEL",
#         },
#         "raw_row": row,
#         "mapped_at": datetime.utcnow().isoformat(),
#     }

#     return claim


# def normalize_record(record):
#     return transform_excel_row_to_claim(record)


# def map_to_claim_schema(data):
#     if data.get("type") == "bulk":
#         return [transform_excel_row_to_claim(row) for row in data.get("records", [])]
#     return transform_excel_row_to_claim(data.get("content", data))

import math
import re
import uuid
from datetime import datetime
from typing import Any


def generate_claim_id() -> str:
    return f"CLM-{uuid.uuid4().hex[:10]}"


def _is_blank(value) -> bool:
    if value is None:
        return True

    if isinstance(value, float) and math.isnan(value):
        return True

    return str(value).strip() == ""


def _get(row: dict, *keys, default=None):
    """
    Case-insensitive row getter.

    Supports Excel columns like:
    - Patient Name
    - patient name
    - patient_name
    - PATIENT NAME
    """
    normalized = {
        _normalize_column_name(key): value
        for key, value in (row or {}).items()
    }

    for key in keys:
        if key in row and not _is_blank(row[key]):
            return row[key]

        normalized_key = _normalize_column_name(key)
        value = normalized.get(normalized_key)

        if not _is_blank(value):
            return value

    return default


def _normalize_column_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _str(row: dict, *keys, default=""):
    value = _get(row, *keys, default=default)

    if _is_blank(value):
        return default

    return str(value).strip()


def _float(row: dict, *keys, default=0.0):
    value = _get(row, *keys, default=default)
    return safe_float(value, default)


def _int(row: dict, *keys, default=1):
    value = _get(row, *keys, default=default)
    return safe_int(value, default)


def _date_string(row: dict, *keys, default=""):
    """
    Convert Excel datetime values to ISO date string.
    Keeps original string if already string.
    """
    value = _get(row, *keys)

    if _is_blank(value):
        return default

    if hasattr(value, "date"):
        return value.date().isoformat()

    return str(value).strip()


def _split_codes(value):
    """
    Split code strings like:
    'E11.9, I10'
    'E11.9|I10'
    'E11.9; I10'
    into a clean list.
    """
    if _is_blank(value):
        return []

    if isinstance(value, list):
        return [
            str(item).strip().upper()
            for item in value
            if not _is_blank(item)
        ]

    return [
        code.strip().upper()
        for code in str(value).replace("|", ",").replace(";", ",").split(",")
        if code.strip()
    ]


def _normalize_claim_type(value, encounter_type="outpatient"):
    raw = (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    if raw in {"CMS1500", "CMS", "PROFESSIONAL", "OUTPATIENT"}:
        return "CMS1500"

    if raw in {"UB04", "UB", "INSTITUTIONAL", "INPATIENT"}:
        return "UB04"

    if raw in {"BOTH", "CMS1500UB04", "UB04CMS1500"}:
        return "BOTH"

    return "UB04" if str(encounter_type).lower() == "inpatient" else "CMS1500"


def _build_services(row: dict) -> list[dict]:
    """
    Build service lines from spreadsheet columns.

    Supports:
    CPT1, CPT 1, Procedure Code 1, HCPCS1
    Charge1, Charge 1, Amount1
    Units1, Units 1
    Modifier1, Modifier 1
    Service Date 1
    """
    services = []

    for index in range(1, 7):
        cpt = _str(
            row,
            f"CPT{index}",
            f"CPT {index}",
            f"Procedure Code {index}",
            f"HCPCS{index}",
            f"HCPCS {index}",
            default="",
        )

        if not cpt and index == 1:
            cpt = _str(
                row,
                "CPT",
                "CPT Code",
                "Procedure Code",
                "HCPCS",
                "Service Code",
                default="",
            )

        if not cpt:
            continue

        service_date = _date_string(
            row,
            f"Service Date {index}",
            f"ServiceDate{index}",
            f"DOS {index}",
            f"DOS{index}",
            "Service Date",
            "Date of Service",
            "DOS",
            default="",
        )

        modifier = _str(
            row,
            f"Modifier{index}",
            f"Modifier {index}",
            "Modifier",
            default="",
        )

        charge = _float(
            row,
            f"Charge{index}",
            f"Charge {index}",
            f"Amount{index}",
            f"Amount {index}",
            "Charge",
            "Amount",
            default=0.0,
        )

        units = _int(
            row,
            f"Units{index}",
            f"Units {index}",
            "Units",
            default=1,
        )

        diagnosis_pointer = _str(
            row,
            f"Diagnosis Pointer {index}",
            f"DiagnosisPointer{index}",
            "Diagnosis Pointer",
            default="1",
        )

        services.append({
            "service_date": service_date,
            "cpt": normalize_code(cpt),
            "modifier": modifier or None,
            "charge": charge,
            "units": units,
            "diagnosis_pointer": diagnosis_pointer,
        })

    return services


def transform_excel_row_to_claim(row: dict, row_number=None, source_file=None) -> dict:
    """
    Convert one Excel/CSV row into the standard downstream claim schema.

    Output is compatible with:
    - EligibilityAgent
    - ValidationAgent
    - ComplianceAgent
    - SubmissionAgent
    """

    row = row or {}
    source_file = source_file or {}

    services = _build_services(row)
    cpt_codes = [
        service["cpt"]
        for service in services
        if service.get("cpt")
    ]

    icd_codes = _split_codes(
        _get(
            row,
            "ICD",
            "ICD10",
            "ICD Code",
            "Diagnosis",
            "Diagnosis Code",
            "diagnosis1",
        )
    )

    total_charge = _float(
        row,
        "Total Charge",
        "Total Amount",
        "Charge",
        "Amount",
        "Billed Amount",
        default=0.0,
    )

    if not total_charge:
        total_charge = sum(
            safe_float(service.get("charge"))
            * safe_int(service.get("units"))
            for service in services
        )

    claim_id = (
        _str(row, "claim_id", "Claim ID", "ClaimID", default="")
        or generate_claim_id()
    )

    encounter_type = _str(
        row,
        "encounter_type",
        "Encounter Type",
        "Claim Type",
        default="outpatient",
    ).lower()

    if encounter_type not in {"outpatient", "inpatient"}:
        encounter_type = (
            "inpatient"
            if encounter_type in {"ub04", "ub-04", "institutional"}
            else "outpatient"
        )

    claim_type = _normalize_claim_type(
        _str(
            row,
            "claim_type",
            "Claim Type",
            "Form Type",
            "Form",
            "CMS Form",
            default="",
        ),
        encounter_type,
    )

    patient_name = _str(
        row,
        "Patient Name",
        "Patient",
        "Name",
        "pt_name",
        default="",
    )

    patient_dob = _date_string(
        row,
        "DOB",
        "Date of Birth",
        "patient_dob",
        "Patient DOB",
        default="",
    )

    provider_npi = normalize_npi(
        _str(
            row,
            "NPI",
            "Provider NPI",
            "billing_provider_npi",
            default="",
        )
    )

    provider_name = _str(
        row,
        "Provider",
        "Provider Name",
        default="",
    )

    payer_name = _str(
        row,
        "Payer",
        "Insurance",
        "Insurance Name",
        "insurance_name",
        default="",
    )

    member_id = _str(
        row,
        "Insurance ID",
        "Member ID",
        "Policy ID",
        "Policy",
        default="",
    )

    claim = {
        "claim_id": claim_id,
        "submission_id": _str(row, "submission_id", "Submission ID", default=claim_id),
        "claim_type": claim_type,
        "encounter_type": encounter_type,

        # Backward-compatible flat fields.
        "patient_name": patient_name,
        "pt_name": patient_name,
        "dob": patient_dob,
        "billing_provider_npi": provider_npi,
        "insurance_name": payer_name,
        "insurance_id": member_id,
        "diagnosis1": icd_codes[0] if icd_codes else "",
        "cpt1": cpt_codes[0] if cpt_codes else "",

        # Standard nested fields used by agents.
        "patient": {
            "name": patient_name,
            "dob": patient_dob,
            "member_id": member_id,
        },
        "provider": {
            "npi": provider_npi,
            "name": provider_name,
        },
        "payer": {
            "name": payer_name,
        },
        "insurance": {
            "member_id": member_id,
            "payer": payer_name,
        },

        "icd_codes": icd_codes,
        "diagnosis_codes": icd_codes,
        "cpt_codes": cpt_codes,
        "services": services,
        "total_charge": total_charge,

        "source": "EXCEL",
        "document_type": "SPREADSHEET",
        "form_type": claim_type,

        "source_file": {
            **source_file,
            "row_number": row_number,
        } if source_file or row_number else {},

        "metadata": {
            "claim_type": claim_type,
            "source_type": "EXCEL",
            "row_number": row_number,
        },

        "raw_row": row,
        "mapped_at": datetime.utcnow().isoformat(),
    }

    extraction_quality = build_extraction_quality(claim)

    claim["extraction"] = {
        **extraction_quality,
        "processor": "claim_mapper",
        "row_number": row_number,
    }
    claim["extraction_confidence"] = extraction_quality["extraction_confidence"]
    claim["confidence"] = extraction_quality["extraction_confidence"]
    claim["missing_fields"] = extraction_quality["missing_fields"]
    claim["requires_human_review"] = extraction_quality["requires_human_review"]

    claim["intake"] = {
        "processor": "claim_mapper",
        "row_number": row_number,
        "confidence": extraction_quality["extraction_confidence"],
    }

    return claim


def build_extraction_quality(claim: dict) -> dict:
    normalized = {
        "patient_name": claim.get("patient", {}).get("name"),
        "member_id": (
            claim.get("insurance", {}).get("member_id")
            or claim.get("patient", {}).get("member_id")
        ),
        "payer_name": claim.get("payer", {}).get("name"),
        "provider_npi": claim.get("provider", {}).get("npi"),
        "diagnosis_codes": claim.get("icd_codes"),
        "service_lines": claim.get("services"),
        "cpt_codes": claim.get("cpt_codes"),
        "total_charge": claim.get("total_charge"),
    }

    required = [
        "patient_name",
        "member_id",
        "service_lines",
    ]

    missing_fields = [
        field
        for field in required
        if not normalized.get(field)
    ]

    present = sum(
        1
        for field in required
        if normalized.get(field)
    )

    confidence = round(present / len(required), 2)

    field_completion = round(
        sum(1 for value in normalized.values() if value)
        / len(normalized)
        * 100
    )

    return {
        **normalized,
        "extraction_confidence": confidence,
        "field_completion": field_completion,
        "service_confidence": 1.0 if claim.get("services") else 0.0,
        "requires_human_review": confidence < 0.7 or bool(missing_fields),
        "missing_fields": missing_fields,
    }


def normalize_npi(value):
    if not value:
        return ""

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

    return digits if len(digits) == 10 else ""


def normalize_code(value):
    if _is_blank(value):
        return ""

    return str(value).strip().upper()


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


def normalize_record(record):
    return transform_excel_row_to_claim(record)


def map_to_claim_schema(data):
    if data.get("type") == "bulk":
        return [
            transform_excel_row_to_claim(row)
            for row in data.get("records", [])
        ]

    return transform_excel_row_to_claim(data.get("content", data))
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.utils.security import mask_presigned_url


s3 = boto3.client("s3")

EDI_OUTPUT_BUCKET = os.environ.get("EDI_OUTPUT_BUCKET")
DDB_TABLE = os.environ.get("DDB_TABLE")

if DDB_TABLE:
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    table = dynamodb.Table(DDB_TABLE)
else:
    table = None


def seg(*elements):
    return "*".join([
        _edi_value(element)
        for element in elements
    ]) + "~"


def _edi_value(value):
    if value is None:
        return ""

    text = str(value)
    return (
        text.replace("~", "")
        .replace("*", "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()

        return float(value or default)

    except (TypeError, ValueError):
        return default


def _safe_int(value, default=1):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _patient_name(claim) -> Tuple[str, str]:
    patient = _safe_dict(claim.get("patient"))

    full_name = (
        claim.get("pt_name")
        or claim.get("patient_name")
        or patient.get("name")
        or ""
    )

    parts = str(full_name).strip().split()

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], ""

    first = parts[0]
    last = " ".join(parts[1:])

    return first, last


def _member_id(claim):
    patient = _safe_dict(claim.get("patient"))
    insurance = _safe_dict(claim.get("insurance"))
    payer = _safe_dict(claim.get("payer"))

    return (
        claim.get("insurance_id")
        or claim.get("member_id")
        or claim.get("subscriber_id")
        or patient.get("member_id")
        or insurance.get("member_id")
        or insurance.get("subscriber_id")
        or payer.get("member_id")
        or "UNKNOWN"
    )


def _claim_id(claim):
    return str(
        claim.get("claim_id")
        or claim.get("submission_id")
        or f"CLM-{uuid.uuid4().hex[:10]}"
    )[:20]


def _normalize_date_yyyymmdd(value):
    if not value:
        return ""

    text = str(value).strip()

    # Already YYYYMMDD
    if len(text) == 8 and text.isdigit():
        return text

    known_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for fmt in known_formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y%m%d")
        except ValueError:
            continue

    digits = "".join(ch for ch in text if ch.isdigit())

    if len(digits) == 8:
        # If starts with year
        if digits[:4].startswith("20") or digits[:4].startswith("19"):
            return digits

        # Assume MMDDYYYY
        return f"{digits[4:8]}{digits[0:2]}{digits[2:4]}"

    return ""


def _service_date(claim):
    services = claim.get("services") or []

    for service in services:
        if not isinstance(service, dict):
            continue

        value = (
            service.get("service_date")
            or service.get("date_of_service")
            or service.get("dos")
            or service.get("from_date")
            or service.get("service_from_date")
        )

        normalized = _normalize_date_yyyymmdd(value)

        if normalized:
            return normalized

    explicit = (
        claim.get("service_date")
        or claim.get("date_of_service")
        or claim.get("dos")
    )

    normalized = _normalize_date_yyyymmdd(explicit)

    if normalized:
        return normalized

    year = claim.get("service_from_yy")
    month = claim.get("service_from_mm")
    day = claim.get("service_from_dd")

    if year and month and day:
        return f"{str(year).zfill(4)}{str(month).zfill(2)}{str(day).zfill(2)}"

    return datetime.utcnow().strftime("%Y%m%d")


def _service_lines(claim) -> List[Dict[str, Any]]:
    services = claim.get("services") or []

    normalized = []

    if isinstance(services, list) and services:
        for index, service in enumerate(services, start=1):
            if not isinstance(service, dict):
                continue

            cpt = (
                service.get("cpt")
                or service.get("cpt_code")
                or service.get("procedure_code")
                or service.get("hcpcs")
            )

            charge = _safe_float(
                service.get("charge")
                or service.get("charge_amount")
                or service.get("amount")
                or service.get("billed_amount")
            )

            units = _safe_int(service.get("units"), 1)

            service_date = (
                service.get("service_date")
                or service.get("date_of_service")
                or service.get("dos")
                or service.get("from_date")
                or service.get("service_from_date")
                or claim.get("service_date")
                or claim.get("date_of_service")
            )

            normalized.append({
                "line": service.get("line") or index,
                "cpt": cpt or "",
                "charge": charge,
                "units": units,
                "service_date": _normalize_date_yyyymmdd(service_date) or _service_date(claim),
                "revenue_code": service.get("revenue_code") or service.get("rev_code") or "0300",
            })

        return normalized

    lines = []

    for index in range(1, 25):
        cpt = claim.get(f"cpt{index}")

        if not cpt:
            continue

        lines.append({
            "line": index,
            "cpt": cpt,
            "charge": _safe_float(
                claim.get(f"cpt{index}_charge")
                or claim.get("total_charge")
            ),
            "units": _safe_int(
                claim.get(f"units_{index}")
                or claim.get(f"units{index}")
                or claim.get("units"),
                1,
            ),
            "service_date": _service_date(claim),
            "revenue_code": claim.get(f"revenue_code{index}") or "0300",
        })

    return lines


def _diagnosis_codes(claim) -> List[str]:
    values = []

    for key in [
        "diagnosis1",
        "diagnosis",
        "diagnosis_codes",
        "icd_codes",
        "icd",
    ]:
        raw = claim.get(key)

        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)

    return list(dict.fromkeys([
        str(value).strip().upper()
        for value in values
        if value
    ]))


def _total_charge(claim, services):
    explicit = _safe_float(claim.get("total_charge"), None)

    if explicit is not None and explicit > 0:
        return explicit

    return round(
        sum(
            _safe_float(service.get("charge")) * _safe_int(service.get("units"))
            for service in services
        ),
        2,
    )


def build_837P(claim):
    claim = claim or {}

    edi = []
    now = datetime.utcnow()
    first_name, last_name = _patient_name(claim)
    services = _service_lines(claim)
    total_charge = _total_charge(claim, services)
    diagnoses = _diagnosis_codes(claim)

    edi.append(seg("ISA", "00", "", "00", "", "ZZ", "SENDERID", "ZZ", "RECEIVERID", now.strftime("%y%m%d"), now.strftime("%H%M"), "U", "00501", "000000001", "0", "P", ":"))
    edi.append(seg("GS", "HC", "SENDERID", "RECEIVERID", now.strftime("%Y%m%d"), now.strftime("%H%M"), "1", "X", "005010X222A1"))
    edi.append(seg("ST", "837", "0001"))
    edi.append(seg("BHT", "0019", "00", _claim_id(claim), now.strftime("%Y%m%d"), now.strftime("%H%M"), "CH"))
    edi.append(seg("NM1", "IL", "1", last_name, first_name, "", "", "MI", _member_id(claim)))
    edi.append(seg("CLM", claim.get("claim_id", "UNKNOWN"), f"{total_charge:.2f}", "", "", "11:B:1", "Y", "A", "Y", "I"))

    if diagnoses:
        edi.append(seg("HI", *[f"ABK:{code}" if index == 0 else f"ABF:{code}" for index, code in enumerate(diagnoses)]))

    for index, service in enumerate(services, start=1):
        edi.append(seg("LX", index))
        edi.append(seg(
            "SV1",
            f"HC:{service.get('cpt', '')}",
            f"{_safe_float(service.get('charge')):.2f}",
            "UN",
            service.get("units", 1),
            "",
            "",
            "1",
        ))
        edi.append(seg("DTP", "472", "D8", service.get("service_date") or _service_date(claim)))

    edi.append(seg("SE", str(len(edi) - 2 + 1), "0001"))
    edi.append(seg("GE", "1", "1"))
    edi.append(seg("IEA", "1", "000000001"))

    return "\n".join(edi)


def build_837I(claim):
    claim = claim or {}

    edi = []
    now = datetime.utcnow()
    first_name, last_name = _patient_name(claim)
    services = _service_lines(claim)
    total_charge = _total_charge(claim, services)
    diagnoses = _diagnosis_codes(claim)
    statement_date = _service_date(claim)

    edi.append(seg("ISA", "00", "", "00", "", "ZZ", "SENDERID", "ZZ", "RECEIVERID", now.strftime("%y%m%d"), now.strftime("%H%M"), "U", "00501", "000000001", "0", "P", ":"))
    edi.append(seg("GS", "HC", "SENDERID", "RECEIVERID", now.strftime("%Y%m%d"), now.strftime("%H%M"), "1", "X", "005010X223A2"))
    edi.append(seg("ST", "837", "0001"))
    edi.append(seg("BHT", "0019", "00", _claim_id(claim), now.strftime("%Y%m%d"), now.strftime("%H%M"), "CH"))
    edi.append(seg("NM1", "IL", "1", last_name, first_name, "", "", "MI", _member_id(claim)))
    edi.append(seg("CLM", claim.get("claim_id", "UNKNOWN"), f"{total_charge:.2f}", "", "", "11:A:1", "Y", "A", "Y", "I"))
    edi.append(seg("DTP", "434", "D8", statement_date))

    if diagnoses:
        edi.append(seg("HI", *[f"BK:{code}" if index == 0 else f"BF:{code}" for index, code in enumerate(diagnoses)]))

    for index, service in enumerate(services, start=1):
        edi.append(seg("LX", index))
        edi.append(seg(
            "SV2",
            service.get("revenue_code") or "0300",
            f"HC:{service.get('cpt', '')}",
            f"{_safe_float(service.get('charge')):.2f}",
            "UN",
            service.get("units", 1),
        ))

    edi.append(seg("SE", str(len(edi) - 2 + 1), "0001"))
    edi.append(seg("GE", "1", "1"))
    edi.append(seg("IEA", "1", "000000001"))

    return "\n".join(edi)


def update_job(job_id, progress, status):
    if not table or not job_id:
        return False

    now = (
        datetime.utcnow() + timedelta(hours=5, minutes=30)
    ).strftime("%Y-%m-%d %H:%M:%S")

    try:
        table.update_item(
            Key={"jobId": job_id},
            UpdateExpression="SET #progress = :p, #ts = :t, #st = :s",
            ExpressionAttributeNames={
                "#progress": "progress",
                "#ts": "updatedAt",
                "#st": "status",
            },
            ExpressionAttributeValues={
                ":p": progress,
                ":t": now,
                ":s": status,
            },
        )
        return True

    except Exception as error:
        print(f"⚠️ [EDIService] DynamoDB job update failed: {str(error)}")
        return False


def process_edi(claim, patient_id, sessionid=None, validated_s3_key=None):
    claim = claim or {}

    encounter = str(
        claim.get("encounter_type")
        or claim.get("claim_type")
        or "outpatient"
    ).lower()

    if encounter == "inpatient":
        edi_text = build_837I(claim)
        suffix = "837I"
    else:
        edi_text = build_837P(claim)
        suffix = "837P"

    if not EDI_OUTPUT_BUCKET:
        return {
            "status": "success",
            "edi_type": suffix,
            "edi_text": edi_text,
            "message": "EDI generated locally; EDI_OUTPUT_BUCKET not configured",
        }

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_patient_id = str(patient_id or claim.get("claim_id") or "UNKNOWN").replace("/", "-")
    edi_key = f"edi/{safe_patient_id}/{safe_patient_id}_{timestamp}_{suffix}.edi"

    try:
        s3.put_object(
            Bucket=EDI_OUTPUT_BUCKET,
            Key=edi_key,
            Body=edi_text.encode("utf-8"),
            ContentType="text/plain",
        )

        update_job(sessionid, progress="EDI", status="SUCCESS")

        download_url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": EDI_OUTPUT_BUCKET,
                "Key": edi_key,
            },
            ExpiresIn=3600,
        )

        print(
            f"✅ [EDIService] EDI generated: bucket={EDI_OUTPUT_BUCKET}, "
            f"key={edi_key}, url={mask_presigned_url(download_url)}"
        )

        response = {
            "status": "success",
            "patient_id": patient_id,
            "edi_key": edi_key,
            "download_url": download_url,
            "masked_download_url": mask_presigned_url(download_url),
            "edi_type": suffix,
        }

        if validated_s3_key:
            response["validated_s3_key"] = validated_s3_key

        return response

    except (BotoCoreError, ClientError) as error:
        print(f"❌ [EDIService] Failed to upload EDI: {str(error)}")
        update_job(sessionid, progress="EDI", status="FAILED")
        return {
            "status": "failed",
            "edi_type": suffix,
            "error": str(error),
            "edi_text": edi_text,
        }


def generate_ub04_edi(claim_data, patient_id, sessionid=None):
    result = process_edi(
        {
            **(claim_data or {}),
            "encounter_type": "inpatient",
        },
        patient_id=patient_id,
        sessionid=sessionid,
    )

    result["form_type"] = "UB-04"

    return result
import os
import time
import re

from app.intake.textract_service import TextractService
from app.intake.textract_service import parse_textract_response
from app.intake.universal_mapper import map_universal_claim
from app.utils.confidence import claim_confidence_status
from app.utils.id_generator import generate_claim_id
from app.websocket.manager import manager
from app.utils.terminal_logger import (
    EMOJI_EXTRACTION,
    EMOJI_SUCCESS,
    log_exception,
    log_terminal,
)


textract = TextractService()

REQUIRED_EXTRACTION_FIELDS = [
    "patient_name",
    "member_id",
    "service_lines",
]


def extract_bucket_key(file_path):
    if not file_path:
        raise ValueError("Missing file path")

    if file_path.startswith("s3://"):
        parts = file_path[5:].split("/", 1)

        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid S3 path format: {file_path}")

        return parts[0], parts[1]

    raise ValueError(f"Invalid S3 path: {file_path}")


async def process_image(file_path, key=None, textract_data=None, claim_id: str = ""):
    """
    Processes image claim files from S3.

    Supports:
    - process_image("s3://bucket/key.png")
    - process_image(bucket, key)

    Returns:
    - normalized claim object for downstream RCM pipeline
    """

    start_time = time.time()

    if key is None:
        bucket, key = extract_bucket_key(file_path)
    else:
        bucket = file_path

    extension = os.path.splitext(key)[1].lower()

    print("\n" + "=" * 80)
    print("🖼️ [ImageProcessor] STARTED")
    print(f"🪣 Bucket: {bucket}")
    print(f"🔑 Key: {key}")
    print(f"📎 Extension: {extension}")
    print("=" * 80)

    log_terminal(
        f"Claim extraction started for image: s3://{bucket}/{key}",
        EMOJI_EXTRACTION,
    )

    await manager.broadcast({
        "event": "intake_image_started",
        "type": "intake_image_started",
        "bucket": bucket,
        "key": key,
        "extension": extension,
        "message": "Image extraction started",
    })

    try:
        # ---------------------------------------------------
        # Step 1: OCR / Textract
        # ---------------------------------------------------
        print("➡️ [1] Running Textract OCR if needed...")

        result = textract_data

        if result is None:
            result = await textract.extract(bucket, key, extension)

        result = result or {}
        blocks = result.get("Blocks", []) if isinstance(result, dict) else []

        print(f"✅ Textract blocks count: {len(blocks)}")

        # ---------------------------------------------------
        # Step 2: Parse Textract response
        # ---------------------------------------------------
        print("➡️ [2] Parsing Textract response...")

        parsed = parse_textract_response(result) or {}

        text = parsed.get("text") or ""
        fields = parsed.get("fields") or {}
        tables = parsed.get("tables") or []

        print(f"✅ Raw text length: {len(text)}")
        print(f"✅ Field count: {len(fields)}")
        print(f"✅ Table count: {len(tables)}")

        # ---------------------------------------------------
        # Step 3: Universal mapping
        # ---------------------------------------------------
        print("➡️ [3] Running universal claim mapper...")

        claim = map_universal_claim({
            **parsed,
            "Blocks": blocks,
        }) or {}

        # ---------------------------------------------------
        # Step 4: Source metadata
        # ---------------------------------------------------
        print("➡️ [4] Adding source metadata...")

        claim_id = (
            claim_id
            or claim.get("claim_id")
            or generate_claim_id()
        )

        source_file = {
            "bucket": bucket,
            "key": key,
            "s3_uri": f"s3://{bucket}/{key}",
            "file_type": "image",
            "extension": extension,
        }

        claim["claim_id"] = claim_id
        claim["source_file"] = source_file

        print(f"✅ Claim ID: {claim_id}")

        # ---------------------------------------------------
        # Step 5: Normalize downstream claim fields
        # ---------------------------------------------------
        print("➡️ [5] Normalizing mapped claim fields...")

        services = normalize_services(claim.get("services") or [])

        services = fill_missing_service_dates_from_text(services, text)

        cpt_codes = extract_cpt_codes(services, claim)
        icd_codes = extract_icd_codes(claim)

        diagnosis_codes = claim.get("diagnosis_codes") or icd_codes

        total_charge = claim.get("total_charge")

        if total_charge is None and services:
            total_charge = sum(
                safe_float(service.get("charge"))
                * safe_int(service.get("units"))
                for service in services
            )

        total_charge = safe_float(total_charge)

        patient = ensure_dict(claim.get("patient"))
        insurance = ensure_dict(claim.get("insurance"))
        payer = ensure_dict(claim.get("payer"))
        provider = ensure_dict(claim.get("provider"))

        member_id = (
            patient.get("member_id")
            or insurance.get("member_id")
            or claim.get("member_id")
        )

        if member_id:
            patient["member_id"] = member_id
            insurance["member_id"] = member_id

        claim["patient"] = patient
        claim["insurance"] = insurance
        claim["payer"] = payer
        claim["provider"] = provider
        claim["services"] = services
        claim["cpt_codes"] = cpt_codes
        claim["icd_codes"] = icd_codes
        claim["diagnosis_codes"] = diagnosis_codes
        claim["total_charge"] = total_charge

        print(f"✅ CPT codes: {cpt_codes}")
        print(f"✅ ICD codes: {icd_codes}")
        print(f"✅ Services extracted: {len(services)}")
        print(f"✅ Total charge: {total_charge}")

        # ---------------------------------------------------
        # Step 6: Form detection
        # ---------------------------------------------------
        print("➡️ [6] Preparing form detection...")

        form_detection = ensure_dict(claim.get("form_detection"))

        document_type = (
            claim.get("document_type")
            or form_detection.get("document_type")
            or form_detection.get("form_type")
            or "GENERIC"
        )

        form_type = (
            claim.get("form_type")
            or form_detection.get("form_type")
            or document_type
        )

        claim["document_type"] = document_type
        claim["form_type"] = form_type
        claim["form_detection"] = form_detection

        await manager.broadcast({
            "event": "form_detected",
            "type": "form_detected",
            "claim_id": claim_id,
            "form_type": form_type,
            "document_type": document_type,
            "confidence": form_detection.get("confidence"),
            "bucket": bucket,
            "key": key,
        })

        print(f"✅ Form type: {form_type}")
        print(f"✅ Document type: {document_type}")

        # ---------------------------------------------------
        # Step 7: Extraction quality
        # ---------------------------------------------------
        print("➡️ [7] Building extraction quality...")

        extraction_quality = build_extraction_quality(claim, parsed)

        duration_seconds = round(time.time() - start_time, 2)
        confidence = extraction_quality["extraction_confidence"]

        claim["extraction"] = {
            **(claim.get("extraction") or {}),
            **extraction_quality,
            "duration_seconds": duration_seconds,
            "raw_fields_count": len(fields),
            "raw_tables_count": len(tables),
            "raw_text_length": len(text),
            "processor": "image_processor",
        }

        claim["extraction_confidence"] = confidence
        claim["confidence"] = confidence
        claim["confidence_status"] = claim_confidence_status(confidence)
        claim["requires_human_review"] = extraction_quality["requires_human_review"]
        claim["missing_fields"] = extraction_quality["missing_fields"]

        claim["extraction_metadata"] = {
            "confidence": confidence,
            "missing_fields": extraction_quality["missing_fields"],
            "raw_fields_count": extraction_quality["raw_fields_count"],
            "raw_tables_count": len(tables),
            "raw_text_length": len(text),
            "duration_seconds": duration_seconds,
            "source_file": source_file,
        }

        claim["intake"] = {
            "processor": "image_processor",
            "document_type": document_type,
            "form_type": form_type,
            "duration_seconds": duration_seconds,
            "service_count": len(services),
            "confidence": confidence,
            "extension": extension,
        }

        print(f"✅ Extraction confidence: {confidence}")
        print(f"✅ Confidence status: {claim['confidence_status']}")
        print(f"✅ Requires human review: {claim['requires_human_review']}")
        print(f"⏱️ Image processing duration: {duration_seconds}s")

        # ---------------------------------------------------
        # Step 8: Frontend extraction completed event
        # ---------------------------------------------------
        await manager.broadcast({
            "event": "extraction_completed",
            "type": "extraction_completed",
            "claim_id": claim_id,
            "processor": "image_processor",
            "form_type": form_type,
            "document_type": document_type,
            "extraction_confidence": confidence,
            "confidence_status": claim.get("confidence_status"),
            "service_count": len(claim.get("services", [])),
            "missing_fields": claim.get("missing_fields", []),
            "requires_human_review": claim.get("requires_human_review"),
            "duration_seconds": duration_seconds,
            "source_file": source_file,
        })

        # ---------------------------------------------------
        # Step 9: Human review status
        # ---------------------------------------------------
        if extraction_quality["requires_human_review"]:
            claim.update({
                "status": "HUMAN_REVIEW_REQUIRED",
                "review_status": "NEEDS_REVIEW",
                "queue_state": "HUMAN_REVIEW",
                "current_stage": "HUMAN_REVIEW",
                "current_step": "human_review_required",
                "active_step": "human_review_required",
                "current_agent": "HUMAN_REVIEW",
                "progress": 45,
                "reason": (
                    "Low extraction confidence"
                    if confidence < 0.7
                    else "Missing required extraction fields"
                ),
            })

        elif claim["confidence_status"]:
            claim["status"] = claim["confidence_status"]

        log_terminal(
            f"Image extraction completed: s3://{bucket}/{key}",
            EMOJI_SUCCESS,
        )

        print("✅ [ImageProcessor] COMPLETED")
        print("=" * 80 + "\n")

        return claim

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [ImageProcessor] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("=" * 80 + "\n")

        log_exception(f"Image claim extraction: s3://{bucket}/{key}", error)

        await manager.broadcast({
            "event": "extraction_failed",
            "type": "extraction_failed",
            "processor": "image_processor",
            "bucket": bucket,
            "key": key,
            "error": str(error),
            "duration_seconds": duration_seconds,
        })

        raise


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

        service_date = (
            service.get("service_date")
            or service.get("date_of_service")
            or service.get("dos")
            or service.get("date")
            or service.get("from_date")
            or service.get("service_from_date")
        )

        service_date = normalize_service_date(service_date)

        charge = safe_float(
            service.get("charge")
            or service.get("charge_amount")
            or service.get("amount")
            or service.get("billed_amount")
        )

        units = safe_int(service.get("units"))

        normalized.append({
            **service,
            "service_date": service_date,
            "date_of_service": service_date,
            "dos": service_date,
            "cpt": cpt,
            "cpt_code": cpt,
            "charge": charge,
            "charge_amount": charge,
            "units": units,
        })

    return normalized


def extract_cpt_codes(services, claim):
    codes = []

    for code in claim.get("cpt_codes", []) or []:
        if code:
            codes.append(str(code).strip())

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
            codes.append(str(code).strip())

    return list(dict.fromkeys(codes))


def extract_icd_codes(claim):
    codes = []

    for key in ["icd_codes", "diagnosis_codes", "diagnoses"]:
        values = claim.get(key) or []

        if isinstance(values, list):
            codes.extend(values)
        elif values:
            codes.append(values)

    return list(dict.fromkeys([
        str(code).strip()
        for code in codes
        if code
    ]))


def build_extraction_quality(claim, parsed):
    normalized = {
        "patient_name": claim.get("patient", {}).get("name"),
        "member_id": (
            claim.get("insurance", {}).get("member_id")
            or claim.get("patient", {}).get("member_id")
        ),
        "payer_name": claim.get("payer", {}).get("name"),
        "diagnosis_codes": claim.get("diagnosis_codes") or claim.get("icd_codes"),
        "service_lines": claim.get("services"),
        "cpt_codes": claim.get("cpt_codes"),
        "total_charge": claim.get("total_charge"),
    }

    missing_fields = [
        field
        for field in REQUIRED_EXTRACTION_FIELDS
        if not normalized.get(field)
    ]

    confidence = calculate_extraction_confidence(normalized)
    requires_review = confidence < 0.7 or len(missing_fields) > 0

    raw_fields_count = len((parsed or {}).get("fields") or {})

    service_count = len(claim.get("services") or [])
    service_confidence = 100 if service_count > 0 else 0

    field_completion = round(
        sum(1 for value in normalized.values() if value)
        / len(normalized)
        * 100
    )

    return {
        **normalized,
        "extraction_confidence": confidence,
        "field_completion": field_completion,
        "service_confidence": service_confidence,
        "requires_human_review": requires_review,
        "missing_fields": missing_fields,
        "raw_fields_count": raw_fields_count,
    }


def calculate_extraction_confidence(normalized):
    present = sum(
        1
        for field in REQUIRED_EXTRACTION_FIELDS
        if normalized.get(field)
    )

    return round(present / len(REQUIRED_EXTRACTION_FIELDS), 2)

def normalize_service_date(value):
    if not value:
        return ""

    value = str(value).strip()

    if "/" in value or "-" in value:
        return value

    return value

def fill_missing_service_dates_from_text(services, text):
    if not services:
        return services

    service_date = extract_first_service_date(text)

    if not service_date:
        return services

    fixed = []

    for service in services:
        if not isinstance(service, dict):
            fixed.append(service)
            continue

        existing_date = (
            service.get("service_date")
            or service.get("date_of_service")
            or service.get("dos")
            or service.get("date")
        )

        if existing_date:
            fixed.append(service)
            continue

        fixed.append({
            **service,
            "service_date": service_date,
            "date_of_service": service_date,
            "dos": service_date,
        })

    return fixed


def extract_first_service_date(text):
    text = str(text or "")

    patterns = [
        r"(?:date\s*of\s*service|service\s*date|dos)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"(?:date\s*of\s*service|service\s*date|dos)\s*[:#-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})\b",
        r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(1).strip()

    return ""

def safe_float(value):
    try:
        if value is None:
            return 0.0

        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()

        return float(value or 0)

    except (TypeError, ValueError):
        return 0.0


def safe_int(value):
    try:
        return int(value or 1)

    except (TypeError, ValueError):
        return 1


def ensure_dict(value):
    return value if isinstance(value, dict) else {}

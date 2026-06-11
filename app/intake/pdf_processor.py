import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.intake.textract_service import TextractService
from app.intake.textract_service import parse_textract_response
from app.intake.form_classifier import detect_document_type
from app.intake.form_normalizer import fix_split_dates, normalize_fields
from app.intake.service_extractor import (
    extract_services,
    extract_services_from_tables,
)
from app.intake.universal_mapper import map_universal_claim
from app.utils.confidence import claim_confidence_status
from app.utils.id_generator import generate_claim_id
from app.websocket.manager import manager
from app.utils.terminal_logger import (
    EMOJI_EXTRACTION,
    EMOJI_PROCESSING,
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


async def process_pdf(bucket: str, key: str, textract_data=None, claim_id: str = ""):
    start_time = time.time()

    print("\n" + "=" * 80)
    print("📄 [PDFProcessor] STARTED")
    print(f"🪣 Bucket: {bucket}")
    print(f"🔑 Key: {key}")
    print("=" * 80)

    log_terminal(
        f"Claim extraction started for PDF: s3://{bucket}/{key}",
        EMOJI_PROCESSING,
    )

    await manager.broadcast(
        {
            "event": "intake_pdf_started",
            "type": "intake_pdf_started",
            "bucket": bucket,
            "key": key,
            "message": "PDF extraction started",
        }
    )

    try:
        # ---------------------------------------------------
        # Step 1: OCR / Textract
        # ---------------------------------------------------
        print("➡️ [1] Running Textract OCR if needed...")

        if textract_data is None:
            log_terminal("OCR started", EMOJI_EXTRACTION)

            textract_data = await textract.extract(
                bucket,
                key,
                ".pdf",
            )

            log_terminal("OCR completed", EMOJI_SUCCESS)

        textract_data = textract_data or {}
        blocks = textract_data.get("Blocks", []) if isinstance(textract_data, dict) else []

        print(f"✅ Textract blocks count: {len(blocks)}")

        # ---------------------------------------------------
        # Step 2: Parse Textract response
        # ---------------------------------------------------
        print("➡️ [2] Parsing Textract response...")

        parsed = parse_textract_response(textract_data) or {}

        text = parsed.get("text") or ""
        fields = parsed.get("fields") or {}
        tables = parsed.get("tables") or []
        lines = parsed.get("lines") or []

        print(f"✅ Raw text length: {len(text)}")
        print(f"✅ Field count: {len(fields)}")
        print(f"✅ Table count: {len(tables)}")
        print("📄 OCR LINES:")

        for line in lines:
            print("   ", line)

        # ---------------------------------------------------
        # Step 3: Detect form type
        # ---------------------------------------------------
        print("➡️ [3] Detecting document type...")

        doc_type = detect_document_type(text) or "GENERIC"

        print(f"✅ Document type detected: {doc_type}")

        # ---------------------------------------------------
        # Step 4: Universal mapping
        # ---------------------------------------------------
        print("➡️ [4] Running universal claim mapper...")

        universal_claim = map_universal_claim(
            {
                **parsed,
                "Blocks": blocks,
            }
        ) or {}

        form_detection = ensure_dict(universal_claim.get("form_detection"))

        form_detection = {
            **form_detection,
            "document_type": doc_type,
            "form_type": (
                doc_type
                if doc_type != "GENERIC"
                else form_detection.get("form_type")
            ),
        }

        await manager.broadcast(
            {
                "event": "form_detected",
                "type": "form_detected",
                "form_type": form_detection.get("form_type"),
                "document_type": doc_type,
                "confidence": form_detection.get("confidence"),
                "bucket": bucket,
                "key": key,
            }
        )

        print("✅ Form detection broadcasted")

        # ---------------------------------------------------
        # Step 5: Normalize fields
        # ---------------------------------------------------
        print("➡️ [5] Normalizing fields...")

        log_terminal("Field normalization started", EMOJI_PROCESSING)

        normalized = normalize_fields(fields) or {}

        if doc_type == "CMS1500":
            text_claim = parse_cms1500(parsed)
        elif doc_type == "UB04":
            text_claim = parse_ub04(parsed)
        else:
            text_claim = parse_generic_claim(parsed)

        text_claim = text_claim or {}

        log_terminal("Field normalization completed", EMOJI_SUCCESS)

        print("✅ Field normalization completed")

        # ---------------------------------------------------
        # Step 6: Extract service lines
        # ---------------------------------------------------
        print("➡️ [6] Extracting service lines...")

        log_terminal("Service extraction started", EMOJI_EXTRACTION)

        if doc_type == "UB04":
            raw_services = (
                text_claim.get("services")
                or extract_services_from_tables(tables)
                or universal_claim.get("services")
                or []
            )

        elif doc_type == "CMS1500":
            raw_services = (
                text_claim.get("services")
                or universal_claim.get("services")
                or extract_services(fields)
                or extract_services_from_tables(tables)
                or []
            )

        else:
            raw_services = (
                universal_claim.get("services")
                or text_claim.get("services")
                or extract_services(fields)
                or extract_services_from_tables(tables)
                or []
            )

        # IMPORTANT: fallback must be outside if/elif/else
        # so it runs for CMS1500 also.
        if not raw_services:
            raw_services = extract_single_service_from_text(text)
            print(f"🧩 Single-service fallback extracted: {len(raw_services)}")

        services = normalize_services(raw_services)

        claim_context = {
            "patient": (
                ensure_dict(universal_claim.get("patient"))
                or ensure_dict(text_claim.get("patient"))
                or {}
            )
        }

        services = clean_pdf_services(
            services,
            claim=claim_context,
            text=text,
        )

        print("🧹 Cleaned PDF services:")
        for index, service in enumerate(services, start=1):
            print(
                f"  #{index}: CPT={service.get('cpt')} "
                f"DOS={service.get('service_date')} "
                f"charge={service.get('charge')} "
                f"desc={service.get('description')}"
            )

        log_terminal(
            f"Service extraction completed: services={len(services)}",
            EMOJI_SUCCESS,
        )

        print(f"✅ Services extracted: {len(services)}")

        # ---------------------------------------------------
        # Step 7: Extract CPT / ICD codes
        # ---------------------------------------------------
        print("➡️ [7] Extracting CPT and ICD codes...")

        cpt_codes = extract_cpt_codes(services, universal_claim)
        icd_codes = extract_icd_codes(universal_claim, text_claim)

        diagnosis_codes = (
            universal_claim.get("diagnosis_codes")
            or icd_codes
        )

        print(f"✅ CPT codes: {cpt_codes}")
        print(f"✅ ICD codes: {icd_codes}")

        # ---------------------------------------------------
        # Step 8: Calculate total charge
        # ---------------------------------------------------
        print("➡️ [8] Calculating total charge...")

        raw_total_charge = (
            universal_claim.get("total_charge")
            or normalized.get("total_charge")
            or text_claim.get("total_charge")
        )

        total_charge = calculate_pdf_total_charge(
            services,
            fallback_total=raw_total_charge,
        )

        print(f"✅ Total charge: {total_charge}")

        # ---------------------------------------------------
        # Step 9: Build final claim object
        # ---------------------------------------------------
        print("➡️ [9] Building final claim object...")

        patient = ensure_dict(universal_claim.get("patient"))
        provider = ensure_dict(universal_claim.get("provider"))
        payer = ensure_dict(
            universal_claim.get("payer")
            or text_claim.get("payer")
        )

        insurance = ensure_dict(universal_claim.get("insurance"))
        text_patient = ensure_dict(text_claim.get("patient"))
        text_provider = ensure_dict(text_claim.get("provider"))
        text_payer = ensure_dict(text_claim.get("payer"))

        claim_id = (
            claim_id
            or universal_claim.get("claim_id")
            or parsed.get("claim_id")
            or generate_claim_id()
        )

        claim = {
            "claim_id": claim_id,
            "source_file": {
                "bucket": bucket,
                "key": key,
                "s3_uri": f"s3://{bucket}/{key}",
                "file_type": "pdf",
            },
            "patient": {
                "name": (
                    patient.get("name")
                    or normalized.get("patient.name")
                    or text_patient.get("name")
                ),
                "dob": fix_split_dates(
                    patient.get("dob")
                    or normalized.get("patient.dob")
                    or text_patient.get("dob")
                ),
                "member_id": (
                    patient.get("member_id")
                    or insurance.get("member_id")
                    or normalized.get("insurance.member_id")
                    or text_payer.get("policy_id")
                ),
            },
            "insurance": {
                "member_id": (
                    insurance.get("member_id")
                    or patient.get("member_id")
                    or normalized.get("insurance.member_id")
                    or text_payer.get("policy_id")
                ),
                "payer": (
                    normalized.get("insurance.payer")
                    or payer.get("name")
                    or text_payer.get("name")
                ),
            },
            "provider": {
                "name": (
                    provider.get("name")
                    or normalized.get("provider.name")
                    or text_provider.get("name")
                ),
                "npi": (
                    provider.get("npi")
                    or normalized.get("provider.npi")
                    or text_provider.get("npi")
                ),
                "tax_id": (
                    provider.get("tax_id")
                    or normalized.get("provider.tax_id")
                    or text_provider.get("tax_id")
                ),
            },
            "payer": payer or {
                "name": (
                    normalized.get("insurance.payer")
                    or text_payer.get("name")
                )
            },
            "diagnosis_codes": diagnosis_codes,
            "icd_codes": icd_codes,
            "cpt_codes": cpt_codes,
            "services": services,
            "total_charge": total_charge,
            "form_type": (
                doc_type
                if doc_type != "GENERIC"
                else universal_claim.get("form_type")
            ),
            "document_type": doc_type,
            "claim_type": universal_claim.get("claim_type") or doc_type,
            "form_detection": form_detection,
            "field_confidence": universal_claim.get("field_confidence", []),
        }

        claim["services"] = clean_pdf_services(
            claim.get("services") or [],
            claim=claim,
            text=text,
        )

        claim["total_charge"] = calculate_pdf_total_charge(
            claim["services"],
            fallback_total=total_charge,
        )

        claim["cpt_codes"] = extract_cpt_codes(
            claim["services"],
            {"cpt_codes": cpt_codes},
        )

        auth_signals = extract_authorization_signals(text)

        claim["authorization_required"] = auth_signals["authorization_required"]
        claim["authorization_number"] = auth_signals["authorization_number"]
        claim["authorization_issue"] = auth_signals["authorization_issue"]
        claim["authorization_reason"] = auth_signals["authorization_reason"]

        claim["denial"] = {
            **ensure_dict(claim.get("denial")),
            **extract_denial_signals(text),
        }

        claim["document_text"] = text

        if doc_type == "EOB_ERA":
            eob_data = extract_eob_codes_and_amount(text)

            claim["document_type"] = "EOB_ERA"
            claim["form_type"] = "EOB_ERA"
            claim["claim_type"] = "EOB_ERA"

            claim["cpt_codes"] = (
                eob_data.get("cpt_codes")
                or claim.get("cpt_codes")
                or []
            )

            claim["icd_codes"] = (
                eob_data.get("icd_codes")
                or claim.get("icd_codes")
                or []
            )

            claim["diagnosis_codes"] = claim["icd_codes"]

            if eob_data.get("total_charge"):
                claim["total_charge"] = eob_data["total_charge"]

            claim["denial_ai_required"] = True
            claim["denial_required"] = True

            claim["status"] = "DENIAL_AI_REQUIRED"
            claim["confidence_status"] = "DENIAL_AI_REQUIRED"
            claim["requires_human_review"] = False

            claim["pipeline_state"] = "DENIAL_DETECTED"
            claim["pipeline_status"] = "DENIAL_AI_REQUIRED"
            claim["current_stage"] = "DENIAL_AI"
            claim["current_agent"] = "DENIAL_AI"
            claim["active_step"] = "denial_ai"

            claim["review_required"] = False
            claim["approval_required"] = False
            claim["pipeline_paused"] = False


        # ---------------------------------------------------
        # Step 10: Extraction quality
        # ---------------------------------------------------
        print("➡️ [10] Building extraction quality...")

        extraction_quality = build_extraction_quality(claim, parsed)

        confidence = extraction_quality["extraction_confidence"]
        duration_seconds = round(time.time() - start_time, 2)

        final_validation_percent = round((extraction_quality.get("extraction_confidence") or 0) * 100)
        final_risk_percent = max(0, 100 - final_validation_percent)

        claim["extraction"] = {
            **(universal_claim.get("extraction") or {}),
            **extraction_quality,

            # Force final PDF processor scores to override stale UniversalMapper scores.
            "extraction_confidence": extraction_quality.get("extraction_confidence"),
            "extraction_confidence_ratio": extraction_quality.get("extraction_confidence"),
            "validation_score": final_validation_percent,
            "validation_score_ratio": round(final_validation_percent / 100, 2),
            "risk_score": final_risk_percent,
            "risk_score_ratio": round(final_risk_percent / 100, 2),
            "field_completion": extraction_quality.get("field_completion"),
            "service_confidence": extraction_quality.get("service_confidence"),
            "service_extraction": extraction_quality.get("service_confidence"),
            "low_confidence": extraction_quality.get("requires_human_review"),

            "duration_seconds": duration_seconds,
            "raw_fields_count": len(fields),
            "raw_tables_count": len(tables),
            "raw_text_length": len(text),
            "processor": "pdf_processor",
            "service_lines": claim.get("services") or [],
            "total_charge": claim.get("total_charge"),
            "cpt_codes": claim.get("cpt_codes") or [],
        }

        if doc_type == "EOB_ERA":
            claim["extraction"].update(
                {
                    "extraction_confidence": max(confidence, 0.9),
                    "extraction_confidence_ratio": max(confidence, 0.9),
                    "validation_score": 90,
                    "validation_score_ratio": 0.9,
                    "risk_score": 10,
                    "risk_score_ratio": 0.1,
                    "low_confidence": False,
                    "requires_human_review": False,
                    "missing_fields": [],
                    "document_category": "denial_document",
                    "processor_route": "denial_ai",
                }
            )
            
        claim["extraction_confidence"] = confidence
        claim["confidence"] = confidence

        if doc_type == "EOB_ERA":
            claim["confidence_status"] = "DENIAL_AI_REQUIRED"
            claim["requires_human_review"] = False
            claim["missing_fields"] = []
        else:
            claim["confidence_status"] = claim_confidence_status(confidence)
            claim["requires_human_review"] = extraction_quality["requires_human_review"]
            claim["missing_fields"] = extraction_quality["missing_fields"]

        claim["extraction_metadata"] = {
            "confidence": confidence,
            "missing_fields": claim.get("missing_fields", extraction_quality["missing_fields"]),
            "raw_fields_count": extraction_quality["raw_fields_count"],
            "raw_tables_count": len(tables),
            "raw_text_length": len(text),
            "duration_seconds": duration_seconds,
            "source_file": claim["source_file"],
        }

        claim["intake"] = {
            "processor": "pdf_processor",
            "document_type": doc_type,
            "duration_seconds": duration_seconds,
            "service_count": len(claim.get("services") or []),
            "confidence": confidence,
        }

        print(f"✅ Extraction confidence: {confidence}")
        print(f"✅ Confidence status: {claim['confidence_status']}")
        print(f"✅ Requires human review: {claim['requires_human_review']}")
        print(f"⏱️ PDF processing duration: {duration_seconds}s")

        log_terminal(
            f"Extraction completed with confidence={confidence:.2f}",
            EMOJI_SUCCESS,
        )

        # ---------------------------------------------------
        # Step 11: Frontend event
        # ---------------------------------------------------
        await manager.broadcast(
            {
                "event": "extraction_completed",
                "type": "extraction_completed",
                "claim_id": claim_id,
                "form_type": claim.get("form_type"),
                "document_type": doc_type,
                "extraction_confidence": claim.get("extraction", {}).get("extraction_confidence"),
                "confidence_status": claim.get("confidence_status"),
                "service_count": len(claim.get("services", [])),
                "missing_fields": claim.get("missing_fields", []),
                "requires_human_review": claim.get("requires_human_review"),
                "duration_seconds": duration_seconds,
                "source_file": claim.get("source_file"),
            }
        )

        # ---------------------------------------------------
        # Step 12: Final routing status
        # ---------------------------------------------------
        is_eob_era = doc_type == "EOB_ERA"

        requires_human_review = bool(
            extraction_quality.get("requires_human_review")
        )

        missing_fields = extraction_quality.get("missing_fields") or []

        if is_eob_era:
            # EOB/ERA denial documents should not be blocked by missing CMS1500
            # service lines. They should continue to Denial AI.
            claim.update(
                {
                    "status": "DENIAL_AI_REQUIRED",
                    "confidence_status": "DENIAL_AI_REQUIRED",
                    "requires_human_review": False,
                    "review_status": None,
                    "queue_state": "DENIAL_AI",
                    "current_stage": "DENIAL_AI",
                    "current_step": "denial_ai",
                    "active_step": "denial_ai",
                    "current_agent": "DENIAL_AI",
                    "progress": 55,
                    "reason": (
                        claim.get("denial", {}).get("denial_reason")
                        or "EOB/ERA denial document detected; routing to Denial AI"
                    ),
                    "denial_ai_required": True,
                    "denial_required": True,
                    "pipeline_state": "DENIAL_DETECTED",
                    "pipeline_status": "DENIAL_AI_REQUIRED",
                    "review_required": False,
                    "approval_required": False,
                    "pipeline_paused": False,
                }
            )

            print("🧠 EOB/ERA detected; bypassing extraction human review and routing to Denial AI")

        elif requires_human_review:
            log_terminal("Extraction requires human review", EMOJI_PROCESSING)

            if confidence < 0.7:
                review_reason = "Low extraction confidence"
            elif missing_fields:
                review_reason = f"Missing required extraction fields: {', '.join(missing_fields)}"
            else:
                review_reason = "Extraction requires human review"

            claim.update(
                {
                    "status": "HUMAN_REVIEW_REQUIRED",
                    "confidence_status": "HUMAN_REVIEW_REQUIRED",
                    "requires_human_review": True,
                    "review_status": "NEEDS_REVIEW",
                    "queue_state": "HUMAN_REVIEW",
                    "current_stage": "HUMAN_REVIEW",
                    "current_step": "human_review_required",
                    "active_step": "human_review_required",
                    "current_agent": "HUMAN_REVIEW",
                    "progress": 45,
                    "reason": review_reason,
                    "pipeline_state": "HUMAN_REVIEW_REQUIRED",
                    "pipeline_status": "HUMAN_REVIEW_REQUIRED",
                    "review_required": True,
                    "approval_required": True,
                    "pipeline_paused": True,
                }
            )

        elif claim.get("confidence_status"):
            claim["status"] = claim["confidence_status"]

            claim.setdefault("pipeline_state", "EXTRACTION_COMPLETED")
            claim.setdefault("pipeline_status", "COMPLETED")
            claim.setdefault("current_stage", "EXTRACTION")
            claim.setdefault("current_step", "extraction")
            claim.setdefault("active_step", "extraction")
            claim.setdefault("current_agent", "OCR / Extraction")
            claim.setdefault("progress", 15)
            claim.setdefault("review_required", False)
            claim.setdefault("approval_required", False)
            claim.setdefault("pipeline_paused", False)

        print("✅ [PDFProcessor] COMPLETED")
        print("=" * 80 + "\n")

        return claim

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [PDFProcessor] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("=" * 80 + "\n")

        log_exception(f"PDF claim extraction: s3://{bucket}/{key}", error)

        await manager.broadcast(
            {
                "event": "extraction_failed",
                "type": "extraction_failed",
                "processor": "pdf_processor",
                "bucket": bucket,
                "key": key,
                "error": str(error),
                "duration_seconds": duration_seconds,
            }
        )

        raise


def parse_cms1500(parsed):
    parsed = parsed or {}

    text = parsed.get("text", "") or ""
    tables = parsed.get("tables", []) or []

    claim = parse_cms1500_text(text) or {}

    # 1. Try table-based service extraction if text parser did not find services.
    if not claim.get("services"):
        claim["services"] = extract_services_from_tables(tables)

    # 2. Fallback for simple key/value CMS1500 PDFs:
    #    CPT: 99213
    #    Units: 1
    #    Date Of Service: 05/22/2026
    #    Place Of Service: 11
    #    Charge Amount: 100.00 USD
    if not claim.get("services"):
        claim["services"] = extract_single_service_from_text(text)

    # 3. Calculate total from extracted service line if missing.
    if not claim.get("total_charge") and claim.get("services"):
        claim["total_charge"] = calculate_pdf_total_charge(claim["services"])

    return claim


def parse_ub04(parsed):
    parsed = parsed or {}
    text_claim = parse_generic_claim(parsed)

    return {
        **text_claim,
        "services": extract_services_from_tables(parsed.get("tables", [])),
    }


def parse_generic_claim(parsed):
    return parse_cms1500_text((parsed or {}).get("text", ""))


def parse_cms1500_text(text):
    claim = {
        "patient": {},
        "provider": {},
        "payer": {},
        "services": [],
        "total_charge": None,
    }

    section = None

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        kv_match = re.match(r"^([A-Za-z ]{2,40})\s*:\s*(.+)$", line)

        if kv_match:
            key = kv_match.group(1).strip()
            value = kv_match.group(2).strip()
            mapped = normalize_fields({key: value}) or {}

            if mapped.get("patient.name"):
                if section == "provider" and key.lower() == "name":
                    claim["provider"]["name"] = value
                    continue

                claim["patient"]["name"] = mapped["patient.name"]
                continue

            if mapped.get("patient.dob"):
                claim["patient"]["dob"] = mapped["patient.dob"]
                continue

            if mapped.get("insurance.member_id"):
                claim["payer"]["policy_id"] = mapped["insurance.member_id"]
                continue

            if mapped.get("insurance.payer"):
                claim["payer"]["name"] = mapped["insurance.payer"]
                continue

            if mapped.get("provider.name"):
                claim["provider"]["name"] = mapped["provider.name"]
                continue

        lower = line.lower()

        if "patient information" in lower:
            section = "patient"
            continue

        if lower.startswith("insurance"):
            section = "payer"
            continue

        if lower.startswith("provider"):
            section = "provider"
            continue

        if lower.startswith("services"):
            section = "services"
            continue

        name_match = re.search(r"\bname\s*:\s*(.+)$", line, re.IGNORECASE)

        if name_match and section in {"patient", "provider"}:
            claim[section]["name"] = name_match.group(1).strip()
            continue

        dob_match = re.search(
            r"\b(?:dob|birth|birth date)\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}(?:/|\s+)[0-9]{1,2}(?:/|\s+)[0-9]{2,4})",
            line,
            re.IGNORECASE,
        )

        if dob_match:
            claim["patient"]["dob"] = fix_split_dates(
                dob_match.group(1).strip()
            )
            continue

        payer_match = re.search(r"\bpayer\s*:\s*(.+)$", line, re.IGNORECASE)

        if payer_match:
            claim["payer"]["name"] = payer_match.group(1).strip()
            continue

        policy_match = re.search(
            r"\bpolicy(?:\s*id)?\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )

        if policy_match:
            claim["payer"]["policy_id"] = policy_match.group(1).strip()
            continue

        npi_match = re.search(r"\bnpi\s*:\s*(\d{10})", line, re.IGNORECASE)

        if npi_match:
            claim["provider"]["npi"] = npi_match.group(1)
            continue

        service_match = re.search(
            r"\bcpt\s*code\s*:\s*(\d{5}).*?\bcharge\s*:\s*\$?([\d,]+(?:\.\d{1,2})?)",
            line,
            re.IGNORECASE,
        )

        if service_match:
            claim["services"].append(
                {
                    "cpt": service_match.group(1),
                    "charge": safe_float(service_match.group(2)),
                    "units": 1,
                }
            )
            continue

        total_match = re.search(
            r"\btotal\s*(?:amount|charge)?\s*:\s*\$?([\d,]+(?:\.\d{1,2})?)",
            line,
            re.IGNORECASE,
        )

        if total_match:
            claim["total_charge"] = safe_float(total_match.group(1))

    return claim


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

        normalized.append(
            {
                **service,
                "service_date": service_date,
                "date_of_service": service_date,
                "dos": service_date,
                "cpt": str(cpt).strip() if cpt else None,
                "cpt_code": str(cpt).strip() if cpt else None,
                "charge": charge,
                "charge_amount": charge,
                "units": units,
            }
        )

    return normalized


def extract_cpt_codes(services, universal_claim):
    codes = []

    for code in (universal_claim or {}).get("cpt_codes", []) or []:
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
            code = str(code).strip()
            if code.isdigit() and len(code) == 5:
                codes.append(code)

    return list(dict.fromkeys(codes))


def extract_icd_codes(universal_claim, text_claim):
    codes = []

    for key in ["icd_codes", "diagnosis_codes", "diagnoses"]:
        values = (universal_claim or {}).get(key) or (text_claim or {}).get(key) or []

        if isinstance(values, list):
            codes.extend(values)
        elif values:
            codes.append(values)

    return list(
        dict.fromkeys(
            [
                str(code).strip()
                for code in codes
                if code
            ]
        )
    )


def normalize_service_date(value):
    if not value:
        return ""

    value = str(value).strip()

    if "/" in value or "-" in value:
        return value

    return value


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


def check_confidence(claim):
    score = 0

    if claim.get("patient", {}).get("name"):
        score += 0.3

    if claim.get("patient", {}).get("dob"):
        score += 0.3

    if claim.get("provider", {}).get("npi"):
        score += 0.2

    if claim.get("services"):
        score += 0.2

    return score


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


def ensure_dict(value):
    return value if isinstance(value, dict) else {}


def _normalize_date_for_compare(value: Any) -> str:
    if not value:
        return ""

    text = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return text


def _normalize_pdf_service(service: dict) -> dict:
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

    units = safe_int(service.get("units"), 1)

    service_date = (
        service.get("service_date")
        or service.get("date_of_service")
        or service.get("dos")
        or service.get("date")
    )

    return {
        **service,
        "cpt": str(cpt).strip() if cpt else None,
        "cpt_code": str(cpt).strip() if cpt else None,
        "charge": charge,
        "charge_amount": charge,
        "units": units,
        "service_date": service_date,
        "date_of_service": service_date,
        "dos": service_date,
    }


def filter_valid_pdf_service_lines(services):
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
        "backend api checks",
        "testing notes",
        "what to check",
        "expected result",
    ]

    for raw_service in services or []:
        if not isinstance(raw_service, dict):
            continue

        service = _normalize_pdf_service(raw_service)

        cpt = str(service.get("cpt") or service.get("cpt_code") or "").strip()
        description = str(service.get("description") or "").lower()
        charge = safe_float(service.get("charge") or service.get("charge_amount"))

        if not cpt.isdigit() or len(cpt) != 5:
            continue

        if any(marker in description for marker in invalid_markers):
            continue

        if charge <= 0:
            continue

        if charge > 10000:
            continue

        cleaned.append(service)

    return cleaned


def _extract_patient_dob_from_claim(claim: dict) -> str:
    if not isinstance(claim, dict):
        return ""

    patient = claim.get("patient") or {}

    return str(
        patient.get("dob")
        or claim.get("patient_dob")
        or claim.get("dob")
        or ""
    ).strip()


def _extract_explicit_service_date_from_text(text: str) -> str:
    text = text or ""

    patterns = [
        r"(?:date\s*of\s*service|service\s*date|dos)\s*[:#-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"(?:date\s*of\s*service|service\s*date|dos)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"\b\d{5}\b\s+[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\s+([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"\b\d{5}\b\s+[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\s+([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    service_section_match = re.search(
        r"Service Lines(?P<section>.*?)(?:Eligibility and Clearinghouse Result|Validation and Compliance Findings|Denial Information|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if service_section_match:
        section = service_section_match.group("section")
        date_match = re.search(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", section)
        if date_match:
            return date_match.group(1).strip()

        date_match = re.search(r"\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})\b", section)
        if date_match:
            return date_match.group(1).strip()

    return ""


def clean_pdf_service_dates(services, claim=None, text=""):
    claim = claim or {}
    patient_dob = _extract_patient_dob_from_claim(claim)
    patient_dob_cmp = _normalize_date_for_compare(patient_dob)
    explicit_service_date = _extract_explicit_service_date_from_text(text)

    cleaned = []

    for service in services or []:
        if not isinstance(service, dict):
            continue

        service = dict(service)

        service_date = str(
            service.get("service_date")
            or service.get("date_of_service")
            or service.get("dos")
            or service.get("date")
            or ""
        ).strip()

        service_date_cmp = _normalize_date_for_compare(service_date)

        if patient_dob_cmp and service_date_cmp == patient_dob_cmp:
            service_date = explicit_service_date or ""

        if not service_date and explicit_service_date:
            service_date = explicit_service_date

        service["service_date"] = service_date or None
        service["date_of_service"] = service_date or None
        service["dos"] = service_date or None

        cleaned.append(service)

    return cleaned


def calculate_pdf_total_charge(services, fallback_total=None):
    calculated_total = sum(
        safe_float(service.get("charge") or service.get("charge_amount"))
        * safe_int(service.get("units"), 1)
        for service in services or []
    )

    if calculated_total > 0:
        return round(calculated_total, 2)

    return safe_float(fallback_total, 0.0)


def clean_pdf_services(services, claim=None, text=""):
    services = filter_valid_pdf_service_lines(services)
    services = clean_pdf_service_dates(services, claim=claim, text=text)
    return services

def extract_authorization_signals(text: str) -> dict:
    """
    Extract prior authorization / precertification signals from OCR text.

    Returns:
    {
        "authorization_required": bool,
        "authorization_number": str | None,
        "authorization_issue": bool,
        "authorization_reason": str | None
    }
    """

    text = str(text or "")
    lower = text.lower()

    # -------------------------------------------------
    # 1. Detect missing / absent authorization language
    # -------------------------------------------------
    missing_phrases = [
        "prior authorization missing",
        "authorization missing",
        "authorization absent",
        "precertification absent",
        "precertification / authorization absent",
        "precertification/authorization absent",
        "authorization was not obtained",
        "authorization number missing",
        "auth_001",
        "precertification absent",
        "precert absent",
    ]

    required_phrases = [
        "prior authorization required",
        "authorization required",
        "precert required",
        "precertification required",
        "requires prior authorization",
        "requires authorization",
        "preauthorization required",
    ]

    authorization_issue = any(phrase in lower for phrase in missing_phrases)

    authorization_required = (
        authorization_issue
        or any(phrase in lower for phrase in required_phrases)
    )

    # -------------------------------------------------
    # 2. Extract authorization number only from strong labels
    # -------------------------------------------------
    authorization_number = None

    auth_number_patterns = [
        # Authorization Number: AUTH12345
        # Prior Authorization Number: AUTH12345
        # Auth No: AUTH12345
        r"\b(?:prior\s+authorization|authorization|prior\s+auth|auth|precertification|precert)\s+"
        r"(?:number|no|#)\s*[:#-]\s*([A-Z0-9][A-Z0-9-]{4,39})\b",

        # Authorization #: AUTH12345
        # Prior Auth #: AUTH12345
        r"\b(?:prior\s+authorization|authorization|prior\s+auth|auth|precertification|precert)\s*#\s*"
        r"([A-Z0-9][A-Z0-9-]{4,39})\b",

        # Prior Auth No AUTH12345
        # Authorization Number AUTH12345
        r"\b(?:prior\s+authorization|authorization|prior\s+auth|auth|precertification|precert)\s+"
        r"(?:number|no|#)\s+([A-Z0-9][A-Z0-9-]{4,39})\b",

        # Prior Authorization: AUTH-789456
        # Authorization: AUTH-789456
        # Auth: AUTH-789456
        # Precertification: AUTH-789456
        r"\b(?:prior\s+authorization|authorization|prior\s+auth|auth|precertification|precert)\s*[:#-]\s*"
        r"([A-Z0-9][A-Z0-9-]{4,39})\b",

        # Prior Authorization AUTH-789456
        # Auth AUTH-789456
        r"\b(?:prior\s+authorization|authorization|prior\s+auth|auth|precertification|precert)\s+"
        r"([A-Z0-9][A-Z0-9-]{4,39})\b",
    ]

    invalid_auth_values = {
        "missing",
        "absent",
        "required",
        "not",
        "none",
        "null",
        "authorization",
        "orization",
        "precertification",
        "precert",
        "auth",
        "number",
        "no",
        "na",
        "n/a",
        "unknown",
        "notrequired",
        "not-required",
        "not_required",
    }

    for pattern in auth_number_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if not match:
            continue

        candidate = match.group(1).strip().strip(".:,;()[]{}")
        candidate_lower = candidate.lower()

        if candidate_lower in invalid_auth_values:
            continue

        if "missing" in candidate_lower or "absent" in candidate_lower:
            continue

        if not re.search(r"\d", candidate):
            continue

        if len(candidate) < 5:
            continue

        authorization_number = candidate
        break

    # -------------------------------------------------
    # 3. If text says missing/absent, force auth number to None
    # -------------------------------------------------
    if authorization_issue:
        authorization_number = None

    # -------------------------------------------------
    # 4. Build reason
    # -------------------------------------------------
    authorization_reason = None

    if authorization_issue:
        authorization_reason = "Authorization number missing or precertification absent"
    elif authorization_required and not authorization_number:
        authorization_reason = "Authorization required but no authorization number found"

    return {
        "authorization_required": authorization_required,
        "authorization_number": authorization_number,
        "authorization_issue": authorization_issue,
        "authorization_reason": authorization_reason,
    }

def extract_denial_signals(text: str) -> dict:
    text = str(text or "")
    lower = text.lower()

    denial_code = None
    denial_code_match = re.search(
        r"denial\s*code\s*[:#-]?\s*([A-Z0-9-]+)",
        text,
        re.IGNORECASE,
    )
    if denial_code_match:
        denial_code = denial_code_match.group(1).strip()

    carc = None
    rarc = None
    carc_rarc_match = re.search(
        r"carc\s*/\s*rarc\s*[:#-]?\s*([A-Z0-9-]+)\s*/\s*([A-Z0-9-]+)",
        text,
        re.IGNORECASE,
    )
    if carc_rarc_match:
        carc = carc_rarc_match.group(1).strip()
        rarc = carc_rarc_match.group(2).strip()

    denial_reason = None
    denial_reason_match = re.search(
        r"denial\s*reason\s*[:#-]?\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if denial_reason_match:
        denial_reason = denial_reason_match.group(1).strip()

    denial_probability = None
    probability_match = re.search(
        r"denial\s*probability\s*[:#-]?\s*(\d{1,3})\s*%",
        text,
        re.IGNORECASE,
    )
    if probability_match:
        denial_probability = int(probability_match.group(1)) / 100

    denied = (
        "denied yes" in lower
        or "denied\n    yes" in lower
        or "claim denied" in lower
        or bool(denial_code)
    )

    return {
        "denied": denied,
        "denial_code": denial_code,
        "carc": carc,
        "rarc": rarc,
        "denial_reason": denial_reason,
        "risk_score": denial_probability,
    }

def extract_eob_codes_and_amount(text: str) -> dict:
    text = str(text or "")

    cpt_match = re.search(
        r"\bCPT\s+Codes?\s*:\s*([0-9,\s]+)",
        text,
        re.IGNORECASE,
    )

    icd_match = re.search(
        r"\bICD\s+Codes?\s*:\s*([A-Z0-9.,\s]+)",
        text,
        re.IGNORECASE,
    )

    amount_match = re.search(
        r"\b(?:Claim\s+Amount|Total\s+Charge|Billed\s+Amount)\s*:\s*\$?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE,
    )

    return {
        "cpt_codes": (
            re.findall(r"\b\d{5}\b", cpt_match.group(1))
            if cpt_match
            else []
        ),
        "icd_codes": (
            re.findall(r"\b[A-Z]\d{2}(?:\.\d+)?\b", icd_match.group(1))
            if icd_match
            else []
        ),
        "total_charge": (
            safe_float(amount_match.group(1))
            if amount_match
            else 0.0
        ),
    }

def extract_single_service_from_text(text: str):
    text = str(text or "")

    cpt_match = re.search(r"\bCPT\s*:\s*(\d{5})\b", text, re.IGNORECASE)
    modifier_match = re.search(r"\bModifier\s*:\s*([A-Z0-9]{1,4})\b", text, re.IGNORECASE)
    units_match = re.search(r"\bUnits\s*:\s*(\d+)\b", text, re.IGNORECASE)

    dos_match = re.search(
        r"\bDate\s+Of\s+Service\s*:\s*"
        r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
        text,
        re.IGNORECASE,
    )

    pos_match = re.search(
        r"\bPlace\s+Of\s+Service\s*:\s*(\d{1,2})\b",
        text,
        re.IGNORECASE,
    )

    charge_match = re.search(
        r"\bCharge\s+Amount\s*:\s*\$?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:USD)?",
        text,
        re.IGNORECASE,
    )

    if not cpt_match:
        return []

    cpt = cpt_match.group(1)
    service_date = dos_match.group(1).strip() if dos_match else None
    charge = safe_float(charge_match.group(1)) if charge_match else 0.0
    units = safe_int(units_match.group(1), 1) if units_match else 1

    return [
        {
            "description": "",
            "cpt": cpt,
            "cpt_code": cpt,
            "modifier": modifier_match.group(1).strip() if modifier_match else None,
            "service_date": service_date,
            "date_of_service": service_date,
            "dos": service_date,
            "place_of_service": pos_match.group(1).strip() if pos_match else None,
            "pos": pos_match.group(1).strip() if pos_match else None,
            "units": units,
            "charge": charge,
            "charge_amount": charge,
            "source": "single_service_text_fallback",
            "confidence": 0.9,
        }
    ]
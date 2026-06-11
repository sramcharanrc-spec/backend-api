import os
import time
from io import BytesIO

import boto3
import pandas as pd

from app.websocket.manager import manager
from app.utils.confidence import claim_confidence_status


s3 = boto3.client("s3")


async def process_excel(bucket: str, key: str, chunk_size=500):
    """
    Processes Excel/CSV files from S3.

    Yields chunks of mapped claim dictionaries.

    Each yielded chunk contains claims in downstream-compatible format:
    patient, provider, payer, services, cpt_codes, icd_codes, total_charge,
    source_file, intake, extraction.
    """

    start_time = time.time()

    print("\n" + "=" * 80)
    print("📊 [ExcelProcessor] STARTED")
    print(f"🪣 Bucket: {bucket}")
    print(f"🔑 Key: {key}")
    print("=" * 80)

    await manager.broadcast({
        "event": "intake_excel_started",
        "type": "intake_excel_started",
        "bucket": bucket,
        "key": key,
        "message": "Excel/CSV extraction started",
    })

    try:
        extension = os.path.splitext(key)[1].lower()

        print("➡️ [1] Downloading file from S3...")

        response = s3.get_object(Bucket=bucket, Key=key)
        file_content = response["Body"].read()

        print(f"✅ File downloaded. Bytes: {len(file_content)}")

        print("➡️ [2] Loading spreadsheet...")

        if extension == ".csv":
            df = pd.read_csv(BytesIO(file_content))
        else:
            df = pd.read_excel(BytesIO(file_content))

        df = df.fillna("")

        total_rows = len(df)
        total_columns = len(df.columns)

        print(f"✅ Total rows: {total_rows}")
        print(f"✅ Total columns: {total_columns}")
        print(f"✅ Columns: {list(df.columns)}")

        await manager.broadcast({
            "event": "excel_loaded",
            "type": "excel_loaded",
            "bucket": bucket,
            "key": key,
            "rows": total_rows,
            "columns": total_columns,
        })

        source_file = {
            "bucket": bucket,
            "key": key,
            "s3_uri": f"s3://{bucket}/{key}",
            "file_type": "spreadsheet",
            "extension": extension,
        }

        for i in range(0, total_rows, chunk_size):
            chunk_start_time = time.time()

            chunk_df = df.iloc[i:i + chunk_size]
            records = chunk_df.to_dict(orient="records")

            print(f"⚡ Processing rows {i + 1} → {i + len(records)}")

            claims = []

            for offset, row in enumerate(records):
                row_number = i + offset + 1

                try:
                    claim = map_excel_row_to_claim(
                        row=row,
                        row_number=row_number,
                        source_file=source_file,
                    )
                    claims.append(claim)

                except Exception as row_error:
                    print(f"⚠️ Row {row_number} failed: {str(row_error)}")

                    claims.append({
                        "claim_id": f"ROW-{row_number}",
                        "source_file": {
                            **source_file,
                            "row_number": row_number,
                        },
                        "status": "ROW_EXTRACTION_FAILED",
                        "error": str(row_error),
                        "requires_human_review": True,
                        "intake": {
                            "processor": "excel_processor",
                            "row_number": row_number,
                        },
                    })

            chunk_duration = round(time.time() - chunk_start_time, 2)
            total_duration = round(time.time() - start_time, 2)

            print(
                f"✅ Chunk completed rows {i + 1} → {i + len(records)} "
                f"in {chunk_duration}s"
            )

            await manager.broadcast({
                "event": "excel_chunk_processed",
                "type": "excel_chunk_processed",
                "bucket": bucket,
                "key": key,
                "start_row": i + 1,
                "end_row": i + len(records),
                "chunk_size": len(records),
                "duration_seconds": chunk_duration,
                "total_duration_seconds": total_duration,
            })

            yield {
                "source_file": source_file,
                "intake": {
                    "processor": "excel_processor",
                    "chunk_start_row": i + 1,
                    "chunk_end_row": i + len(records),
                    "chunk_size": len(records),
                    "duration_seconds": chunk_duration,
                    "total_duration_seconds": total_duration,
                },
                "claims": claims,
            }

        duration_seconds = round(time.time() - start_time, 2)

        await manager.broadcast({
            "event": "excel_extraction_completed",
            "type": "excel_extraction_completed",
            "bucket": bucket,
            "key": key,
            "rows": total_rows,
            "columns": total_columns,
            "duration_seconds": duration_seconds,
        })

        print("✅ [ExcelProcessor] COMPLETED")
        print(f"⏱️ Total duration: {duration_seconds}s")
        print("=" * 80 + "\n")

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [ExcelProcessor] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("=" * 80 + "\n")

        await manager.broadcast({
            "event": "excel_extraction_failed",
            "type": "excel_extraction_failed",
            "bucket": bucket,
            "key": key,
            "error": str(error),
            "duration_seconds": duration_seconds,
        })

        raise


def map_excel_row_to_claim(row, row_number, source_file):
    """
    Maps one Excel/CSV row into the standard claim shape.
    Supports multiple possible column names.
    """

    row = normalize_row(row)

    patient_name = first_value(
        row,
        "patient_name",
        "Patient Name",
        "patient",
        "Patient",
        "name",
        "Name",
    )

    patient_dob = first_value(
        row,
        "patient_dob",
        "Patient DOB",
        "dob",
        "DOB",
        "date_of_birth",
        "Date of Birth",
    )

    member_id = first_value(
        row,
        "member_id",
        "Member ID",
        "insured_id",
        "Insured ID",
        "policy_id",
        "Policy ID",
    )

    payer_name = first_value(
        row,
        "payer",
        "payer_name",
        "Payer",
        "Payer Name",
        "insurance",
        "Insurance",
    )

    provider_name = first_value(
        row,
        "provider",
        "provider_name",
        "Provider",
        "Provider Name",
    )

    provider_npi = first_value(
        row,
        "provider_npi",
        "Provider NPI",
        "npi",
        "NPI",
    )

    provider_tax_id = first_value(
        row,
        "tax_id",
        "Tax ID",
        "provider_tax_id",
        "Provider Tax ID",
    )

    cpt = first_value(
        row,
        "cpt",
        "cpt_code",
        "CPT",
        "CPT Code",
        "procedure_code",
        "Procedure Code",
        "hcpcs",
        "HCPCS",
    )

    icd = first_value(
        row,
        "icd",
        "icd_code",
        "ICD",
        "ICD Code",
        "diagnosis_code",
        "Diagnosis Code",
        "diagnosis",
        "Diagnosis",
    )

    service_date = first_value(
        row,
        "service_date",
        "Service Date",
        "date_of_service",
        "Date of Service",
        "dos",
        "DOS",
    )

    units = safe_int(first_value(
        row,
        "units",
        "Units",
        "quantity",
        "Quantity",
    ))

    charge = safe_float(first_value(
        row,
        "charge",
        "Charge",
        "amount",
        "Amount",
        "billed_amount",
        "Billed Amount",
        "total_charge",
        "Total Charge",
    ))

    claim_id = first_value(
        row,
        "claim_id",
        "Claim ID",
        "claim_number",
        "Claim Number",
    ) or f"ROW-{row_number}"

    services = []

    if cpt or charge:
        services.append({
            "service_date": service_date,
            "cpt": str(cpt).strip() if cpt else None,
            "units": units,
            "charge": charge,
        })

    cpt_codes = [str(cpt).strip()] if cpt else []
    icd_codes = [str(icd).strip()] if icd else []

    total_charge = charge if charge else sum(
        safe_float(service.get("charge")) * safe_int(service.get("units"))
        for service in services
    )

    claim = {
        "claim_id": claim_id,
        "source_file": {
            **source_file,
            "row_number": row_number,
        },
        "patient": {
            "name": patient_name,
            "dob": patient_dob,
            "member_id": member_id,
        },
        "insurance": {
            "member_id": member_id,
            "payer": payer_name,
        },
        "payer": {
            "name": payer_name,
        },
        "provider": {
            "name": provider_name,
            "npi": provider_npi,
            "tax_id": provider_tax_id,
        },
        "services": services,
        "cpt_codes": cpt_codes,
        "icd_codes": icd_codes,
        "diagnosis_codes": icd_codes,
        "total_charge": total_charge,
        "document_type": "SPREADSHEET",
        "form_type": "SPREADSHEET",
        "intake": {
            "processor": "excel_processor",
            "row_number": row_number,
        },
    }

    extraction_quality = build_extraction_quality(claim)

    claim["extraction"] = {
        **extraction_quality,
        "processor": "excel_processor",
        "row_number": row_number,
    }

    claim["extraction_confidence"] = extraction_quality["extraction_confidence"]
    claim["confidence"] = extraction_quality["extraction_confidence"]
    claim["confidence_status"] = claim_confidence_status(
        extraction_quality["extraction_confidence"]
    )
    claim["requires_human_review"] = extraction_quality["requires_human_review"]
    claim["missing_fields"] = extraction_quality["missing_fields"]

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
            "reason": "Missing required spreadsheet fields",
        })

    elif claim["confidence_status"]:
        claim["status"] = claim["confidence_status"]

    return claim


def normalize_row(row):
    normalized = {}

    for key, value in row.items():
        original_key = str(key).strip()
        clean_key = (
            original_key
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

        normalized[original_key] = value
        normalized[clean_key] = value

    return normalized


def first_value(row, *keys):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)

    return None


def build_extraction_quality(claim):
    normalized = {
        "patient_name": claim.get("patient", {}).get("name"),
        "member_id": (
            claim.get("insurance", {}).get("member_id")
            or claim.get("patient", {}).get("member_id")
        ),
        "payer_name": claim.get("payer", {}).get("name"),
        "provider_identifier": (
            claim.get("provider", {}).get("npi")
            or claim.get("provider", {}).get("tax_id")
        ),
        "diagnosis_codes": claim.get("diagnosis_codes") or claim.get("icd_codes"),
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
        "service_confidence": 100 if claim.get("services") else 0,
        "requires_human_review": confidence < 0.7 or bool(missing_fields),
        "missing_fields": missing_fields,
    }


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
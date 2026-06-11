


import os
import uuid
import time
import asyncio
import logging
import re

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List

from app.intake.router import route_file
from app.intake.claim_mapper import transform_excel_row_to_claim
from app.intake.extraction_store import persist_extraction_metadata
from app.rcm.rcm_graph import rcm_graph
from app.rcm.claim_store import bulk_insert_claims, create_case, save_claim
from app.queue.queue_manager import claim_queue
from app.websocket.manager import manager
from app.services.field_normalizer import FieldNormalizer
from app.services.analytics_service import update_extraction_metrics
from app.utils.confidence import (
    calculate_confidence,
    claim_confidence_status,
    normalize_confidence_score,
)
from app.utils.id_generator import generate_claim_id
from app.utils.terminal_logger import (
    EMOJI_ERROR,
    EMOJI_PROCESSING,
    EMOJI_START,
    EMOJI_SUCCESS,
    EMOJI_UPLOAD,
    TerminalStepLogger,
)

logger = logging.getLogger("rcm_processor")
logger.setLevel(logging.INFO)


# -------------------------
# CONFIG
# -------------------------
CONCURRENT_LIMIT = min(50, (os.cpu_count() or 4) * 5)

CHUNK_SIZE = 500
BULK_QUEUE_CHUNK_SIZE = int(os.getenv("BULK_QUEUE_CHUNK_SIZE", "50"))

MAX_CONCURRENT_CLAIM_PIPELINES = int(
    os.getenv("MAX_CONCURRENT_CLAIM_PIPELINES", "10")
)

NORMALIZATION_TIMEOUT = int(os.getenv("NORMALIZATION_TIMEOUT", "30"))
BATCH_PROCESSING_TIMEOUT = int(os.getenv("BATCH_PROCESSING_TIMEOUT", "120"))
MIN_NORMALIZATION_CONFIDENCE = float(
    os.getenv("MIN_NORMALIZATION_CONFIDENCE", "0.8")
)


# -------------------------
# METRICS
# -------------------------
@dataclass
class ProcessingMetrics:
    total_processed: int = 0
    successful_claims: int = 0
    failed_claims: int = 0
    hitl_required: int = 0
    normalization_timeouts: int = 0
    validation_failures: int = 0
    processing_time_total: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def success_rate(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return round((self.successful_claims / self.total_processed) * 100, 2)


metrics = ProcessingMetrics()


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


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


def safe_str(value, default=""):
    if value is None:
        return default

    value = str(value).strip()

    return value if value else default


def claim_source_file(bucket, key):
    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
    }


def force_claim_identity(claim, claim_id, bucket, key):
    if not isinstance(claim, dict):
        return claim

    claim["claim_id"] = claim_id
    claim["id"] = claim_id
    claim["source_file"] = claim_source_file(bucket, key)
    claim["file_name"] = key
    claim["filename"] = key

    return claim


async def retry_wrapper(func, retries=3, initial_delay=1, backoff_factor=2):
    """
    Retry async operations with exponential backoff.
    """

    delay = initial_delay

    for attempt in range(retries):
        try:
            return await func()

        except Exception as error:
            if attempt == retries - 1:
                logger.error(
                    "Failed after %s attempts: %s",
                    retries,
                    str(error),
                )
                raise

            logger.warning(
                "Attempt %s/%s failed. Retrying in %ss: %s",
                attempt + 1,
                retries,
                delay,
                str(error),
            )

            await asyncio.sleep(delay)
            delay *= backoff_factor


# -------------------------
# DLQ
# -------------------------
async def send_to_dlq(
    claim_id: str,
    error: str,
    claim_data: dict,
    metadata: dict | None = None,
):
    """
    Store failed claim information as a DLQ case for later review.
    """

    dlq_record = {
        "claim_id": claim_id,
        "timestamp": utc_now_iso(),
        "error": error,
        "claim_data": claim_data,
        "metadata": metadata or {},
        "dlq_status": "PENDING_REVIEW",
    }

    try:
        create_case(
            claim_id=claim_id,
            error=error,
            case_type="DLQ",
            metadata=dlq_record,
        )

        logger.info("Claim %s sent to DLQ: %s", claim_id, error)

    except Exception as dlq_error:
        logger.error(
            "Failed to send claim %s to DLQ: %s",
            claim_id,
            str(dlq_error),
        )

    return dlq_record


# -------------------------
# QUALITY SCORING
# -------------------------
def score_normalization_quality(raw_data: Any, cleaned_data: Any) -> float:
    """
    Estimate how much normalization changed the extracted data.

    Higher score means the normalized data is close to the original extraction.
    Lower score means heavy correction occurred and review may be needed.
    """

    try:
        if isinstance(raw_data, list) and isinstance(cleaned_data, list):
            if len(raw_data) != len(cleaned_data):
                return 0.5

            scores = [
                score_normalization_quality(raw_item, clean_item)
                for raw_item, clean_item in zip(raw_data, cleaned_data)
            ]

            return sum(scores) / len(scores) if scores else 0.5

        if isinstance(raw_data, dict) and isinstance(cleaned_data, dict):
            if not raw_data or not cleaned_data:
                return 0.5

            matching_fields = 0
            total_fields = max(len(raw_data), len(cleaned_data))

            for key in raw_data.keys():
                if key not in cleaned_data:
                    continue

                raw_value = str(raw_data[key]).lower().strip()
                clean_value = str(cleaned_data[key]).lower().strip()

                if raw_value == clean_value:
                    matching_fields += 1

                elif raw_value in clean_value or clean_value in raw_value:
                    matching_fields += 0.7

            return matching_fields / total_fields if total_fields else 0.5

        return 0.5

    except Exception as error:
        logger.warning("Quality score calculation failed: %s", str(error))
        return 0.5


# -------------------------
# REQUIRED FIELD HELPERS
# -------------------------
QUEUE_REQUIRED_FIELDS = [
    "patient.name",
    "insurance.member_id",
    "services",
]


def _value_at_path(data: dict, path: str):
    current = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(part)

    return current


def _has_required_value(value) -> bool:
    if value in (None, "", [], {}):
        return False

    if isinstance(value, str):
        return value.strip().lower() not in {
            "unknown",
            "n/a",
            "na",
            "none",
            "null",
        }

    return True


def ensure_required_claim_aliases(claim: dict) -> dict:
    """
    Fill common alias locations so queue validation can work consistently.
    """

    if not isinstance(claim, dict):
        return claim

    patient = claim.setdefault("patient", {})

    if isinstance(patient, dict) and not _has_required_value(patient.get("name")):
        patient["name"] = (
            claim.get("patient_name")
            or claim.get("pt_name")
            or patient.get("name")
        )

    insurance = claim.setdefault("insurance", {})

    if isinstance(insurance, dict) and not _has_required_value(
        insurance.get("member_id")
    ):
        payer = claim.get("payer") if isinstance(claim.get("payer"), dict) else {}
        patient = claim.get("patient") if isinstance(claim.get("patient"), dict) else {}

        insurance["member_id"] = (
            claim.get("insurance_id")
            or claim.get("member_id")
            or claim.get("policy_id")
            or payer.get("policy_id")
            or payer.get("member_id")
            or patient.get("member_id")
            or insurance.get("member_id")
        )

    if isinstance(insurance, dict) and not _has_required_value(
        insurance.get("payer")
    ):
        payer = claim.get("payer") if isinstance(claim.get("payer"), dict) else {}

        insurance["payer"] = (
            payer.get("name")
            or claim.get("insurance_name")
            or insurance.get("payer")
        )

    return claim


def missing_required_fields_before_queue(claim: dict) -> List[str]:
    claim = ensure_required_claim_aliases(claim)

    return [
        field
        for field in QUEUE_REQUIRED_FIELDS
        if not _has_required_value(_value_at_path(claim, field))
    ]


def missing_fields_response(claim: dict, missing: List[str]) -> dict:
    return {
        "success": False,
        "status": "MISSING_FIELDS",
        "claim_id": (claim or {}).get("claim_id"),
        "missing": missing,
        "payload": claim,
    }


def _requires_human_review_before_queue(claim: dict) -> bool:
    claim = claim or {}

    document_type = str(
        claim.get("document_type")
        or claim.get("form_type")
        or claim.get("claim_type")
        or ""
    ).upper()

    status = str(
        claim.get("status")
        or claim.get("confidence_status")
        or claim.get("pipeline_status")
        or ""
    ).upper()

    if (
        document_type == "EOB_ERA"
        or claim.get("denial_ai_required") is True
        or status == "DENIAL_AI_REQUIRED"
    ):
        return False

    return (
        claim.get("requires_human_review") is True
        or status in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED"}
    )


def human_review_required_response(
    claim: dict,
    missing: List[str] | None = None,
) -> dict:
    claim = ensure_required_claim_aliases(claim or {})

    claim_id = claim.get("claim_id") or generate_claim_id()

    missing = (
        missing
        or claim.get("missing_fields")
        or claim.get("extraction_metadata", {}).get("missing_fields")
        or []
    )

    reason = claim.get("reason") or (
        "Missing required extraction fields"
        if missing
        else "Low confidence extraction"
    )

    try:
        progress = max(int(float(claim.get("progress") or 45)), 45)
    except (TypeError, ValueError):
        progress = 45

    claim.update({
        "claim_id": claim_id,
        "status": "HUMAN_REVIEW_REQUIRED",
        "review_status": "NEEDS_REVIEW",
        "review_state": "NEEDS_REVIEW",
        "queue_state": "HUMAN_REVIEW",
        "current_stage": "HUMAN_REVIEW",
        "current_step": "human_review_required",
        "active_step": "human_review_required",
        "current_agent": "HUMAN_REVIEW",
        "requires_human_review": True,
        "reason": reason,
        "missing_fields": missing,
        "progress": progress,
    })

    try:
        save_claim(
            claim_id,
            "HUMAN_REVIEW_REQUIRED",
            "HUMAN_REVIEW",
            claim,
            total_charge=claim.get("total_charge", 0),
        )

        create_case(
            claim_id=claim_id,
            error=reason,
            case_type="HITL",
            metadata={
                "missing": missing,
                "reason": reason,
                "queue_state": "HUMAN_REVIEW",
                "review_status": "NEEDS_REVIEW",
            },
        )

    except Exception as error:
        logger.warning(
            "Failed to persist pre-queue HITL claim %s: %s",
            claim_id,
            str(error),
        )

    return {
        "success": False,
        "status": "HUMAN_REVIEW_REQUIRED",
        "claim_id": claim_id,
        "missing": missing,
        "reason": reason,
        "payload": claim,
    }


# -------------------------
# CONFIDENCE
# -------------------------
def _effective_claim_confidence(source: str, claim: dict) -> float:
    extraction = (
        claim.get("extraction")
        if isinstance(claim.get("extraction"), dict)
        else {}
    )

    metadata = (
        claim.get("extraction_metadata")
        if isinstance(claim.get("extraction_metadata"), dict)
        else {}
    )

    existing = normalize_confidence_score(
        metadata.get("confidence")
        or claim.get("confidence")
        or claim.get("extraction_confidence")
        or extraction.get("extraction_confidence_ratio")
        or extraction.get("extraction_confidence")
        or extraction.get("confidence_score")
        or extraction.get("confidence")
        or extraction.get("ocr_confidence")
    )

    if existing is not None:
        return existing

    return calculate_confidence(source, claim)


# -------------------------
# FALLBACK PARSER
# -------------------------
def extract_structured_data(raw_text: str) -> dict:
    """
    Last-resort parser.

    It should not invent charges. If charge is missing, return zero and let
    manual review handle it.
    """

    raw_text = str(raw_text or "")

    name_match = re.search(r"\bName:\s*(.+)", raw_text, re.IGNORECASE)

    cpt_codes = re.findall(
        r"\b(?:CPT|HCPCS|Procedure)\s*Code?\s*:\s*(\d{5})",
        raw_text,
        re.IGNORECASE,
    )

    if not cpt_codes:
        cpt_codes = re.findall(r"\b\d{5}\b", raw_text)

    total_match = re.search(
        r"\bTotal\s*(?:Amount|Charge)?\s*:\s*\$?([\d,]+(?:\.\d{1,2})?)",
        raw_text,
        re.IGNORECASE,
    )

    total_amount = (
        safe_float(total_match.group(1))
        if total_match
        else 0.0
    )

    return {
        "patient_name": name_match.group(1).strip() if name_match else "",
        "cpt_codes": list(dict.fromkeys(cpt_codes)),
        "total_amount": total_amount,
    }


# -------------------------
# LEGACY WRAPPERS
# -------------------------
async def process_document(bucket, key):
    """
    Deprecated compatibility wrapper.

    New flow should use process_document_async().
    """

    return await process_document_async(bucket, key)


async def process_tabular_file(file_path):
    """
    Deprecated.

    The new flow uses route_file() with S3 input.
    """

    raise NotImplementedError(
        "process_tabular_file is deprecated. Use process_document_async()."
    )


# -------------------------
# PIPELINE
# -------------------------
def initial_pipeline_steps() -> Dict[str, bool]:
    return {
        "eligibility_checked": False,
        "rules_validated": False,
        "compliance_checked": False,
        "case_orchestrated": False,
        "submitted": False,
        "acknowledged": False,
        "denial_checked": False,
        "payment_processed": False,
        "paid": False,
        "underpaid": False,
        "payment_denied": False,
        "feedback_captured": False,
        "learning_updated": False,
        "analytics_done": False,
    }


def final_status_from_steps(steps: Dict[str, Any]) -> str:
    """
    Decide final status from LangGraph pipeline steps.
    """

    if steps.get("submitted") and not steps.get("acknowledged"):
        return "PENDING_APPROVAL"

    if (
        steps.get("payment_processed")
        and steps.get("learning_updated")
        and steps.get("analytics_done")
    ):
        return "COMPLETED"

    if (
        steps.get("payment_processed")
        and steps.get("feedback_captured")
        and steps.get("learning_updated")
        and steps.get("analytics_done")
    ):
        return "COMPLETED"

    if steps.get("payment_denied"):
        return "DENIED"

    if steps.get("underpaid"):
        return "UNDERPAID"

    return "PROCESSING"


async def run_claim_pipeline(mapped_claim):
    """
    Run one claim through LangGraph.
    """

    mapped_claim = mapped_claim or {}
    mapped_claim.setdefault("claim_id", generate_claim_id())

    claim_id = mapped_claim["claim_id"]

    if not mapped_claim.get("cpt_codes"):
        mapped_claim["cpt_codes"] = [
            service.get("cpt")
            for service in mapped_claim.get("services", [])
            if isinstance(service, dict) and service.get("cpt")
        ]

    if not mapped_claim.get("diagnosis_codes") and mapped_claim.get("icd_codes"):
        mapped_claim["diagnosis_codes"] = mapped_claim["icd_codes"]

    state = {
        "claim": mapped_claim,
        "stage": "start",
        "pipeline": {
            "steps": initial_pipeline_steps()
        },
    }

    try:
        pipeline_result = await retry_wrapper(
            lambda: rcm_graph.ainvoke(state),
            retries=2,
            initial_delay=1,
            backoff_factor=2,
        )

    except Exception as error:
        logger.error("LangGraph failed for %s: %s", claim_id, str(error))
        pipeline_result = state
        pipeline_result["error"] = str(error)

    if not isinstance(pipeline_result, dict):
        pipeline_result = state

    final_claim = pipeline_result.get("claim") or mapped_claim
    pipeline = pipeline_result.get("pipeline") or state.get("pipeline")

    if not isinstance(pipeline, dict):
        pipeline = {"steps": initial_pipeline_steps()}

    steps = pipeline.setdefault("steps", {})

    validation = (
        pipeline_result.get("validation")
        or final_claim.get("validation")
        or {}
    )

    if validation.get("valid") is False:
        try:
            create_case(
                claim_id=claim_id,
                error=validation.get("errors", ["Validation failed"]),
                case_type="HITL",
                metadata={"validation": validation},
            )
        except Exception:
            logger.exception("Failed to create HITL case")

        return {
            "claim_id": claim_id,
            "status": "HITL_REQUIRED",
            "payload": final_claim,
            "pipeline": pipeline,
            "validation": validation,
        }

    status = pipeline_result.get("status") or final_status_from_steps(steps)

    return {
        "claim_id": claim_id,
        "status": status,
        "payload": final_claim,
        "pipeline": pipeline,
        "validation": validation,
    }


async def process_single_claim(row, source_type):
    """
    Process a single tabular claim row.
    """

    mapped_claim = (
        row
        if isinstance(row, dict) and row.get("patient") and row.get("services")
        else transform_excel_row_to_claim(row)
    )

    mapped_claim.setdefault("source", source_type)

    result = await retry_wrapper(
        lambda: run_claim_pipeline(mapped_claim),
        retries=3,
        initial_delay=1,
        backoff_factor=2,
    )

    try:
        await manager.send_event("progress", "updated", {
            "claim_id": result["claim_id"],
            "status": result["status"],
            "claim_type": result.get("payload", {}).get("claim_type"),
        })
    except Exception as error:
        logger.warning(
            "WebSocket progress update failed for %s: %s",
            result.get("claim_id"),
            str(error),
        )

    return result


async def process_claims_batch(data: List[dict], source_type: str):
    """
    Process multiple claim records with concurrency and timeout protection.
    """

    logger.info("Starting batch processing: %s claims", len(data))

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    start_time = time.time()

    async def worker(index, row):
        async with semaphore:
            return await process_single_claim(row, source_type)

    tasks = [
        worker(index, row)
        for index, row in enumerate(data)
    ]

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=BATCH_PROCESSING_TIMEOUT,
        )

    except asyncio.TimeoutError:
        metrics.failed_claims += len(data)
        metrics.total_processed += len(data)

        return {
            "total": len(data),
            "success": 0,
            "failed": len(data),
            "error": "Processing timeout",
        }

    bulk_data = []
    success = 0
    failed = 0
    hitl_count = 0
    dlq_count = 0

    for index, result in enumerate(results):
        if isinstance(result, Exception):
            failed += 1
            metrics.failed_claims += 1

            await send_to_dlq(
                claim_id=f"BATCH-{index}",
                error=str(result),
                claim_data=data[index],
                metadata={
                    "batch_index": index,
                    "source": "process_claims_batch",
                },
            )

            dlq_count += 1
            continue

        status = str(result.get("status") or "").upper()

        if status in {
            "COMPLETED",
            "PROCESSING",
            "PENDING_APPROVAL",
            "QUEUED",
            "PAID",
        }:
            success += 1
            metrics.successful_claims += 1
        else:
            failed += 1
            metrics.failed_claims += 1

        if status in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED"}:
            hitl_count += 1
            metrics.hitl_required += 1

        if status == "VALIDATION_FAILED":
            metrics.validation_failures += 1

        bulk_data.append({
            "claim_id": result["claim_id"],
            "status": result["status"],
            "payload": result.get("payload"),
            "pipeline": result.get("pipeline", {}),
            "claim_type": result.get("payload", {}).get("claim_type"),
        })

    metrics.total_processed += len(data)

    for index in range(0, len(bulk_data), CHUNK_SIZE):
        chunk = bulk_data[index:index + CHUNK_SIZE]
        bulk_insert_claims(chunk)

    elapsed = round(time.time() - start_time, 2)
    metrics.processing_time_total += elapsed

    return {
        "total": len(data),
        "success": success,
        "failed": failed,
        "hitl_count": hitl_count,
        "dlq_count": dlq_count,
        "processing_time_seconds": elapsed,
        "cumulative_metrics": metrics.to_dict(),
    }


# -------------------------
# QUEUE HELPERS
# -------------------------
def chunk_claims(items: List[dict], size: int = BULK_QUEUE_CHUNK_SIZE):
    for index in range(0, len(items), size):
        yield index // size, items[index:index + size]


def prepare_claim_for_queue(
    claim: dict,
    source: str,
    processing_mode: str,
    upload_session_id: str,
    temp_id: str,
    upload_type: str,
):
    upload_timestamp = utc_now_iso()

    claim.setdefault("claim_id", generate_claim_id())
    claim.setdefault("source", source)

    claim["processing_mode"] = str(processing_mode or "MANUAL").upper()
    claim["clearinghouse_processing_mode"] = str(processing_mode or "MANUAL").upper()
    claim["upload_session_id"] = upload_session_id
    claim["bulk_session_id"] = upload_session_id or temp_id or f"BULK-{uuid.uuid4().hex[:10]}"
    claim["temp_id"] = temp_id
    claim["upload_type"] = upload_type

    claim.setdefault("created_at", upload_timestamp)
    claim.setdefault("uploaded_at", upload_timestamp)
    claim["last_activity_at"] = upload_timestamp
    claim["is_new_upload"] = True

    claim.setdefault("status", "QUEUED")
    claim.setdefault("current_stage", "QUEUE")
    claim.setdefault("active_step", "queued")
    claim.setdefault("current_agent", "QUEUE")
    claim.setdefault("progress", 1)

    return ensure_required_claim_aliases(claim)


async def emit_bulk_progress(bulk_session_id: str, **fields):
    await manager.broadcast({
        "type": "bulk_progress",
        "event": "bulk_progress",
        "bulk_session_id": bulk_session_id,
        "timestamp": utc_now_iso(),
        **fields,
    })


async def process_claim_chunk_async(
    claims: List[dict],
    bulk_session_id: str = "",
    chunk_index: int = 0,
    total_chunks: int = 1,
):
    """
    Run a queued bulk chunk through LangGraph.
    """

    start_time = time.time()
    total = len(claims)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CLAIM_PIPELINES)

    counters = {
        "processed": 0,
        "completed": 0,
        "failed": 0,
        "hitl": 0,
    }

    manager.register_bulk_claims(
        bulk_session_id,
        [claim.get("claim_id") for claim in claims],
    )

    await emit_bulk_progress(
        bulk_session_id,
        status="RUNNING",
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        chunk_total=total,
        processed=0,
        remaining=total,
    )

    async def run_one(claim: dict):
        async with semaphore:
            claim = ensure_required_claim_aliases(claim)
            claim_id = claim.get("claim_id")

            try:
                missing = missing_required_fields_before_queue(claim)

                if missing:
                    counters["failed"] += 1
                    return missing_fields_response(claim, missing)

                if _requires_human_review_before_queue(claim):
                    counters["hitl"] += 1
                    return human_review_required_response(claim, missing)

                result = await run_claim_pipeline(claim)
                status = str(result.get("status") or "UNKNOWN").upper()

                if status in {
                    "COMPLETED",
                    "PAID",
                    "PROCESSING",
                    "PENDING_APPROVAL",
                    "WAITING_FOR_APPROVAL",
                }:
                    counters["completed"] += 1

                elif status in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED"}:
                    counters["hitl"] += 1

                else:
                    counters["failed"] += 1

                return result

            except Exception as error:
                counters["failed"] += 1

                await send_to_dlq(
                    claim_id=claim_id or f"BULK-{chunk_index}-{uuid.uuid4().hex[:8]}",
                    error=str(error),
                    claim_data=claim,
                    metadata={
                        "bulk_session_id": bulk_session_id,
                        "chunk_index": chunk_index,
                    },
                )

                return {
                    "claim_id": claim_id,
                    "status": "FAILED",
                    "error": str(error),
                }

            finally:
                counters["processed"] += 1

                if counters["processed"] == total or counters["processed"] % 10 == 0:
                    await emit_bulk_progress(
                        bulk_session_id,
                        status="RUNNING",
                        chunk_index=chunk_index,
                        total_chunks=total_chunks,
                        chunk_total=total,
                        processed=counters["processed"],
                        remaining=max(total - counters["processed"], 0),
                        completed=counters["completed"],
                        failed=counters["failed"],
                        hitl=counters["hitl"],
                    )

    results = await asyncio.gather(
        *(run_one(claim) for claim in claims),
        return_exceptions=False,
    )

    elapsed = round(time.time() - start_time, 3)

    await emit_bulk_progress(
        bulk_session_id,
        status="COMPLETED",
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        chunk_total=total,
        processed=total,
        remaining=0,
        completed=counters["completed"],
        failed=counters["failed"],
        hitl=counters["hitl"],
        duration_seconds=elapsed,
    )

    await manager.flush_bulk_session(bulk_session_id)

    return {
        "status": "COMPLETED",
        "bulk_session_id": bulk_session_id,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "total": total,
        "completed": counters["completed"],
        "failed": counters["failed"],
        "hitl": counters["hitl"],
        "duration_seconds": elapsed,
        "results": results,
    }


# -------------------------
# METRICS API HELPERS
# -------------------------
async def get_processing_metrics():
    return {
        "timestamp": utc_now_iso(),
        "metrics": metrics.to_dict(),
        "success_rate_percent": f"{metrics.success_rate:.1f}%",
    }


async def reset_metrics():
    global metrics

    old_metrics = metrics.to_dict()
    metrics = ProcessingMetrics()

    logger.info("Metrics reset. Old metrics: %s", old_metrics)

    return {
        "status": "reset",
        "previous_metrics": old_metrics,
        "reset_time": utc_now_iso(),
    }


# -------------------------
# MAIN FILE PROCESSOR
# -------------------------
async def process_document_async(
    bucket,
    key,
    processing_mode="MANUAL",
    upload_session_id="",
    temp_id="",
    claim_id="",
):
    """
    Main background processor for uploaded original files.

    Flow:
    1. Route file to PDF/image/Excel extractor
    2. Normalize extracted data
    3. Structure claims
    4. Persist extraction metadata
    5. Queue single or bulk claims
    6. Emit frontend progress events
    """

    start_time = time.time()
    terminal = TerminalStepLogger("process_document_async")

    claim_id = claim_id or generate_claim_id()
    final_results = []

    try:
        terminal.log(
            f"Claim processing started: bucket={bucket}, key={key}",
            EMOJI_START,
        )

        logger.info("Starting processing: bucket=%s, key=%s", bucket, key)

        ext = os.path.splitext(key)[1].lower()
        filename = os.path.basename(key)
        route_path = f"s3://{bucket}/{key}"

        source_file = {
            "bucket": bucket,
            "key": key,
            "s3_uri": route_path,
            "filename": filename,
            "extension": ext,
        }

        terminal.log("Original uploaded file received", EMOJI_UPLOAD)

        await manager.broadcast({
            "type": "OCR_STARTED",
            "event": "OCR_STARTED",
            "claim_id": claim_id,
            "id": claim_id,
            "stage": "OCR Extraction",
            "filename": filename,
            "s3_key": key,
            "upload_session_id": upload_session_id,
            "temp_id": temp_id,
        })

        terminal.log(f"File type detected: {ext}", EMOJI_PROCESSING)
        terminal.log(f"Routing file for extraction: {route_path}", EMOJI_PROCESSING)

        async for raw_chunk in route_file(route_path, key, bucket, claim_id=claim_id):
            chunk_size = (
                len(raw_chunk.get("claims", []))
                if isinstance(raw_chunk, dict) and isinstance(raw_chunk.get("claims"), list)
                else len(raw_chunk)
                if isinstance(raw_chunk, list)
                else 1
            )

            terminal.log(
                f"Extraction completed for chunk: size={chunk_size}",
                EMOJI_SUCCESS,
            )

            await manager.broadcast({
                "type": "VALIDATION_STARTED",
                "event": "VALIDATION_STARTED",
                "claim_id": claim_id,
                "id": claim_id,
                "stage": "Validation Running",
                "filename": filename,
                "s3_key": key,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
            })

            cleaned = await normalize_raw_chunk(raw_chunk)

            quality_score = score_normalization_quality(raw_chunk, cleaned)

            if quality_score < MIN_NORMALIZATION_CONFIDENCE:
                logger.warning("Low quality normalization: %s", quality_score)

            structured_claim = structure_claim_chunk(
                raw_chunk=raw_chunk,
                cleaned=cleaned,
                source_file=source_file,
            )

            source = infer_source(structured_claim, cleaned)

            if isinstance(structured_claim, dict):
                force_claim_identity(structured_claim, claim_id, bucket, key)

                enrich_single_claim(
                    structured_claim,
                    source=source,
                    processing_mode=processing_mode,
                    upload_session_id=upload_session_id,
                    temp_id=temp_id,
                    source_file=source_file,
                )

                force_claim_identity(structured_claim, claim_id, bucket, key)

                await emit_single_claim_created(
                    structured_claim,
                    upload_session_id,
                    temp_id,
                    filename,
                    key,
                )

                persist_metadata_safely(structured_claim, raw_chunk)

                result = await queue_single_claim(structured_claim)
                result["claim_id"] = claim_id
                result["id"] = claim_id
                final_results.append(result)

            elif isinstance(structured_claim, list):
                result = await queue_bulk_claims(
                    claims=structured_claim,
                    raw_chunk=raw_chunk,
                    source=source,
                    processing_mode=processing_mode,
                    upload_session_id=upload_session_id,
                    temp_id=temp_id,
                    filename=filename,
                    s3_key=key,
                    source_file=source_file,
                )

                final_results.append(result)

        queued = any(result.get("status") == "QUEUED" for result in final_results)

        missing_only = (
            final_results
            and all(result.get("status") == "MISSING_FIELDS" for result in final_results)
        )

        review_only = (
            final_results
            and all(
                result.get("status") in {"HUMAN_REVIEW_REQUIRED", "HITL_REQUIRED"}
                for result in final_results
            )
        )

        duration_seconds = round(time.time() - start_time, 2)

        response_status = (
            "QUEUED"
            if queued
            else "MISSING_FIELDS"
            if missing_only
            else "HUMAN_REVIEW_REQUIRED"
            if review_only
            else "COMPLETED"
        )

        await manager.broadcast({
            "type": "intake_completed",
            "event": "intake_completed",
            "claim_id": claim_id,
            "id": claim_id,
            "status": response_status,
            "bucket": bucket,
            "key": key,
            "duration_seconds": duration_seconds,
            "jobs": final_results,
        })

        if len(final_results) == 1 and final_results[0].get("status") in {
            "MISSING_FIELDS",
            "HUMAN_REVIEW_REQUIRED",
            "HITL_REQUIRED",
        }:
            final_results[0].setdefault("id", final_results[0].get("claim_id") or claim_id)
            return final_results[0]

        return {
            "success": queued,
            "status": response_status,
            "claim_id": claim_id,
            "id": claim_id,
            "bucket": bucket,
            "key": key,
            "duration_seconds": duration_seconds,
            "jobs": final_results,
        }

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        logger.error("Critical error: %s", str(error), exc_info=True)

        terminal.log(f"Processing failed: {str(error)}", EMOJI_ERROR)

        await manager.broadcast({
            "type": "claim_processing_failed",
            "event": "claim_processing_failed",
            "claim_id": claim_id,
            "status": "FAILED",
            "stage": "extraction",
            "filename": os.path.basename(key),
            "s3_key": key,
            "error": str(error),
            "duration_seconds": duration_seconds,
        })

        await send_to_dlq(
            claim_id=claim_id or f"UNKNOWN-{uuid.uuid4().hex[:8]}",
            error=str(error),
            claim_data={
                "bucket": bucket,
                "key": key,
            },
            metadata={
                "source": "process_document_async",
            },
        )

        return {
            "status": "FAILED",
            "claim_id": claim_id,
            "id": claim_id,
            "error": str(error),
            "bucket": bucket,
            "key": key,
            "duration_seconds": duration_seconds,
        }


# -------------------------
# MAIN PROCESSOR HELPERS
# -------------------------
async def normalize_raw_chunk(raw_chunk):
    """
    Normalize extracted chunk with FieldNormalizer unless it is already a
    final claim/extraction object.
    """

    if (
        isinstance(raw_chunk, dict)
        and (
            raw_chunk.get("services")
            or raw_chunk.get("claims")
            or raw_chunk.get("status") == "HITL_REQUIRED"
            or raw_chunk.get("requires_human_review") is True
            or raw_chunk.get("extraction_metadata")
        )
    ):
        return raw_chunk

    normalizer = FieldNormalizer()

    try:
        return await asyncio.wait_for(
            normalizer.normalize(raw_chunk),
            timeout=NORMALIZATION_TIMEOUT,
        )

    except asyncio.TimeoutError:
        metrics.normalization_timeouts += 1
        logger.warning("Normalization timeout. Using raw chunk.")
        return raw_chunk

    except Exception as error:
        logger.warning("Normalization failed. Using raw chunk: %s", str(error))
        return raw_chunk


def structure_claim_chunk(raw_chunk, cleaned, source_file):
    """
    Convert normalized extraction output into either:
    - one claim dict
    - list of claim dicts
    """

    if isinstance(cleaned, dict) and isinstance(cleaned.get("claims"), list):
        claims = []

        for claim in cleaned["claims"]:
            if not isinstance(claim, dict):
                continue

            claim.setdefault("source_file", source_file)
            claims.append(claim)

        return claims

    if isinstance(cleaned, list):
        claims = []

        for row_number, row in enumerate(cleaned, start=1):
            if not isinstance(row, dict):
                continue

            if row.get("patient") and row.get("services"):
                claim = row
                claim.setdefault("source_file", {
                    **source_file,
                    "row_number": row_number,
                })
            else:
                claim = transform_excel_row_to_claim(
                    row=row,
                    row_number=row_number,
                    source_file=source_file,
                )

            claims.append(claim)

        return claims

    if (
        isinstance(cleaned, dict)
        and (
            cleaned.get("services")
            or cleaned.get("requires_human_review") is True
            or cleaned.get("extraction_metadata")
        )
    ):
        cleaned.setdefault("source_file", source_file)
        return cleaned

    if isinstance(raw_chunk, dict):
        try:
            mapped = map_universal_claim(raw_chunk)
            mapped.setdefault("source_file", source_file)
            return mapped

        except Exception as error:
            logger.warning("Universal extraction fallback failed: %s", str(error))

    fallback = extract_structured_data(str(raw_chunk))

    services = [
        {
            "cpt": cpt,
            "charge": 0,
            "units": 1,
            "missing_charge": True,
            "source": "fallback_parser",
        }
        for cpt in fallback.get("cpt_codes", [])
    ]

    missing_fields = []

    if not fallback.get("patient_name"):
        missing_fields.append("patient.name")

    if not services:
        missing_fields.append("services")

    if not fallback.get("total_amount"):
        missing_fields.append("total_charge")

    return {
        "claim_id": generate_claim_id(),
        "patient": {
            "name": fallback.get("patient_name") or "",
            "dob": "",
        },
        "provider": {},
        "payer": {},
        "insurance": {},
        "services": services,
        "cpt_codes": fallback.get("cpt_codes", []),
        "icd_codes": [],
        "diagnosis_codes": [],
        "total_charge": fallback.get("total_amount") or 0,
        "source_file": source_file,
        "source": "FALLBACK",
        "requires_human_review": True,
        "missing_fields": missing_fields,
        "reason": "Fallback extraction used; manual review required",
    }


def infer_source(structured_claim, cleaned) -> str:
    if isinstance(structured_claim, list):
        return "EXCEL"

    if isinstance(structured_claim, dict):
        if structured_claim.get("source"):
            return structured_claim["source"]

        if structured_claim.get("form_detection"):
            return "UNIVERSAL_OCR"

        if structured_claim.get("source_file", {}).get("file_type") == "spreadsheet":
            return "EXCEL"

    if isinstance(cleaned, dict) and cleaned.get("claims"):
        return "EXCEL"

    return "AI"


def enrich_single_claim(
    claim,
    source,
    processing_mode,
    upload_session_id,
    temp_id,
    source_file,
):
    upload_timestamp = utc_now_iso()

    claim.setdefault("claim_id", generate_claim_id())
    claim.setdefault("source_file", source_file)
    claim.setdefault("source", source)

    claim["processing_mode"] = str(processing_mode or "MANUAL").upper()
    claim["clearinghouse_processing_mode"] = str(processing_mode or "MANUAL").upper()
    claim["upload_session_id"] = upload_session_id
    claim["temp_id"] = temp_id

    claim.setdefault("created_at", upload_timestamp)
    claim.setdefault("uploaded_at", upload_timestamp)
    claim["last_activity_at"] = upload_timestamp
    claim["is_new_upload"] = True

    confidence = _effective_claim_confidence(source, claim)

    document_type = str(
        claim.get("document_type")
        or claim.get("form_type")
        or claim.get("claim_type")
        or ""
    ).upper()

    is_denial_ai_claim = (
        document_type == "EOB_ERA"
        or claim.get("denial_ai_required") is True
        or str(claim.get("status") or "").upper() == "DENIAL_AI_REQUIRED"
    )

    claim["confidence"] = confidence

    if is_denial_ai_claim:
        claim["status"] = "DENIAL_AI_REQUIRED"
        claim["confidence_status"] = "DENIAL_AI_REQUIRED"
        claim["requires_human_review"] = False
        claim["pipeline_state"] = "DENIAL_DETECTED"
        claim["pipeline_status"] = "DENIAL_AI_REQUIRED"
        claim["current_stage"] = "DENIAL_AI"
        claim["current_agent"] = "DENIAL_AI"
        claim["active_step"] = "denial_ai"
    else:
        claim["confidence_status"] = claim_confidence_status(confidence)

    extraction = claim.get("extraction", {})

    if isinstance(extraction, dict):
        update_extraction_metrics_safely(extraction, claim)


async def emit_single_claim_created(
    claim,
    upload_session_id,
    temp_id,
    filename,
    s3_key,
):
    claim_id = claim.get("claim_id")
    upload_timestamp = claim.get("created_at") or utc_now_iso()

    await manager.broadcast({
        "type": "new_claim_uploaded",
        "event": "new_claim_uploaded",
        "claim_id": claim_id,
        "upload_type": "single",
        "upload_session_id": upload_session_id,
        "temp_id": temp_id,
        "created_at": upload_timestamp,
        "claim": claim,
    })

    await manager.broadcast({
        "type": "claim_created",
        "event": "claim_created",
        "claim_id": claim_id,
        "upload_session_id": upload_session_id,
        "temp_id": temp_id,
        "claim": claim,
        "stage": "Claim Created",
    })

    await manager.broadcast({
        "type": "CLAIM_SAVED",
        "event": "CLAIM_SAVED",
        "claim_id": claim_id,
        "stage": "Saving Claim",
        "filename": filename,
        "s3_key": s3_key,
        "upload_session_id": upload_session_id,
        "temp_id": temp_id,
    })

    extraction = claim.get("extraction", {})

    if isinstance(extraction, dict):
        await manager.broadcast({
            "event": "validation_scored",
            "type": "validation_scored",
            "claim_id": claim_id,
            "validation_score": extraction.get("validation_score"),
            "extraction_confidence": extraction.get("extraction_confidence"),
            "risk_score": extraction.get("risk_score"),
        })

        if extraction.get("low_confidence"):
            await manager.broadcast({
                "event": "low_confidence_detected",
                "type": "low_confidence_detected",
                "claim_id": claim_id,
                "extraction_confidence": extraction.get("extraction_confidence"),
            })


def update_extraction_metrics_safely(extraction, claim):
    try:
        update_extraction_metrics(
            form_type=extraction.get("form_type") or claim.get("form_type"),
            ocr_quality=extraction.get("ocr_quality", 0),
            extraction_confidence=extraction.get("extraction_confidence", 0),
            validation_score=extraction.get("validation_score", 0),
            service_confidence=extraction.get("service_confidence", 0),
            low_confidence=extraction.get("low_confidence", False),
        )

    except Exception as error:
        logger.warning("Extraction metrics update failed: %s", str(error))


def persist_metadata_safely(claim, raw_chunk):
    if not isinstance(claim, dict):
        return

    if not claim.get("field_confidence") and not claim.get("extraction"):
        return

    try:
        persist_extraction_metadata(
            claim["claim_id"],
            claim,
            raw_chunk if isinstance(raw_chunk, dict) else {},
        )

    except Exception as error:
        logger.warning("Extraction metadata persistence failed: %s", str(error))


async def queue_single_claim(claim):
    claim = ensure_required_claim_aliases(claim or {})

    missing = missing_required_fields_before_queue(claim)

    document_type = str(
        claim.get("document_type")
        or claim.get("form_type")
        or claim.get("claim_type")
        or ""
    ).upper()

    status = str(
        claim.get("status")
        or claim.get("confidence_status")
        or claim.get("pipeline_status")
        or ""
    ).upper()

    is_denial_ai_claim = (
        document_type == "EOB_ERA"
        or claim.get("denial_ai_required") is True
        or status == "DENIAL_AI_REQUIRED"
    )

    if is_denial_ai_claim:
        claim.update(
            {
                "status": "DENIAL_AI_REQUIRED",
                "confidence_status": "DENIAL_AI_REQUIRED",
                "requires_human_review": False,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "queue_state": "DENIAL_AI",
                "pipeline_state": "DENIAL_DETECTED",
                "pipeline_status": "DENIAL_AI_REQUIRED",
                "current_stage": "DENIAL_AI",
                "current_agent": "DENIAL_AI",
                "current_step": "denial_ai",
                "active_step": "denial_ai",
                "denial_ai_required": True,
                "denial_required": True,
                "progress": 55,
            }
        )

        missing = []

    if not is_denial_ai_claim and _requires_human_review_before_queue(claim):
        result = human_review_required_response(claim, missing)

        await manager.broadcast(
            {
                "type": "manual_review_required",
                "event": "manual_review_required",
                "claim_id": result.get("claim_id"),
                "status": "HUMAN_REVIEW_REQUIRED",
                "stage": "HUMAN_REVIEW",
                "progress": result.get("payload", {}).get("progress", 45),
                "claim": result.get("payload"),
            }
        )

        return result

    if not is_denial_ai_claim and missing:
        return missing_fields_response(claim, missing)

    job = claim_queue.enqueue(
        "app.queue.jobs.process_claim_job",
        claim,
        job_timeout=300,
    )

    print(f"📤 Job queued: {job.id}")

    await manager.broadcast(
        {
            "type": "claim_queued",
            "event": "claim_queued",
            "claim_id": claim.get("claim_id"),
            "status": claim.get("status") or "QUEUED",
            "stage": claim.get("current_stage") or "QUEUE",
            "progress": claim.get("progress", 10),
            "claim": claim,
            "job_id": job.id,
        }
    )

    return {
        "claim_id": claim.get("claim_id"),
        "job_id": job.id,
        "status": "QUEUED",
        "queued_stage": claim.get("current_stage"),
        "pipeline_status": claim.get("pipeline_status"),
        "denial_ai_required": claim.get("denial_ai_required", False),
    }

async def queue_bulk_claims(
    claims,
    raw_chunk,
    source,
    processing_mode,
    upload_session_id,
    temp_id,
    filename,
    s3_key,
    source_file,
):
    bulk_session_id = upload_session_id or temp_id or f"BULK-{uuid.uuid4().hex[:10]}"

    prepared_claims = [
        prepare_claim_for_queue(
            claim=claim,
            source=source,
            processing_mode=processing_mode,
            upload_session_id=bulk_session_id,
            temp_id=temp_id,
            upload_type="bulk",
        )
        for claim in claims
    ]

    missing_results = []
    valid_claims = []

    for claim in prepared_claims:
        claim.setdefault("source_file", source_file)

        missing = missing_required_fields_before_queue(claim)

        if _requires_human_review_before_queue(claim):
            review_result = human_review_required_response(claim, missing)
            missing_results.append(review_result)

            await manager.broadcast({
                "type": "manual_review_required",
                "event": "manual_review_required",
                "claim_id": review_result.get("claim_id"),
                "status": "HUMAN_REVIEW_REQUIRED",
                "stage": "HUMAN_REVIEW",
                "progress": review_result.get("payload", {}).get("progress", 45),
                "claim": review_result.get("payload"),
            })

            continue

        if missing:
            missing_results.append(missing_fields_response(claim, missing))
            continue

        valid_claims.append(claim)

    if not valid_claims:
        return {
            "status": "MISSING_FIELDS",
            "bulk_session_id": bulk_session_id,
            "missing_fields": missing_results,
        }

    total_claims = len(valid_claims)
    chunks = list(chunk_claims(valid_claims, BULK_QUEUE_CHUNK_SIZE))
    job_ids = []

    await manager.broadcast({
        "type": "bulk_upload_started",
        "event": "bulk_upload_started",
        "bulk_session_id": bulk_session_id,
        "upload_session_id": upload_session_id,
        "temp_id": temp_id,
        "total_claims": total_claims,
        "chunk_size": BULK_QUEUE_CHUNK_SIZE,
        "total_chunks": len(chunks),
        "filename": filename,
        "timestamp": utc_now_iso(),
    })

    queued_records = [
        {
            "claim_id": claim["claim_id"],
            "status": "QUEUED",
            "stage": "QUEUE",
            "total_charge": claim.get("total_charge", 0),
            "payload": claim,
        }
        for claim in valid_claims
    ]

    for _, db_chunk in chunk_claims(queued_records, CHUNK_SIZE):
        bulk_insert_claims(db_chunk)

    queued_count = 0

    for chunk_index, claims_chunk in chunks:
        for claim in claims_chunk:
            await manager.broadcast({
                "type": "claim_created",
                "event": "claim_created",
                "claim_id": claim.get("claim_id"),
                "bulk_session_id": bulk_session_id,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
                "status": "QUEUED",
                "stage": "Claim Queued",
                "claim": {
                    "claim_id": claim.get("claim_id"),
                    "status": "QUEUED",
                    "patient": claim.get("patient"),
                    "payer": claim.get("payer"),
                    "total_charge": claim.get("total_charge"),
                    "bulk_session_id": bulk_session_id,
                    "upload_session_id": upload_session_id,
                    "upload_type": "bulk",
                },
            })

            persist_metadata_safely(claim, raw_chunk)

        job = claim_queue.enqueue(
            "app.queue.jobs.process_claim_chunk_job",
            claims_chunk,
            bulk_session_id,
            chunk_index,
            len(chunks),
            job_timeout=1800,
        )

        job_ids.append(job.id)
        queued_count += len(claims_chunk)

        await emit_bulk_progress(
            bulk_session_id,
            status="QUEUED",
            chunk_index=chunk_index,
            total_chunks=len(chunks),
            queued=queued_count,
            remaining=max(total_claims - queued_count, 0),
        )

    await manager.broadcast({
        "type": "bulk_upload_queued",
        "event": "bulk_upload_queued",
        "bulk_session_id": bulk_session_id,
        "total_claims": total_claims,
        "total_chunks": len(chunks),
        "job_ids": job_ids,
        "timestamp": utc_now_iso(),
    })

    return {
        "status": "QUEUED",
        "bulk_session_id": bulk_session_id,
        "total_claims": total_claims,
        "missing_fields": missing_results,
        "total_chunks": len(chunks),
        "total_jobs": len(job_ids),
        "job_ids": job_ids,
    }

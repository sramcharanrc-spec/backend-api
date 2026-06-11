import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from boto3 import resource
from rq import get_current_job

from app.intake.processor import (
    ensure_required_claim_aliases,
    missing_fields_response,
    missing_required_fields_before_queue,
    process_claim_chunk_async,
    process_document_async,
)
from app.rcm.claim_store import create_case, save_claim
from app.rcm.pipeline import run_claim_pipeline
from app.rcm.pipeline_observability import emit_pipeline_event, pipeline_log
from app.utils.confidence import claim_confidence_status
from app.utils.terminal_logger import (
    EMOJI_ERROR,
    EMOJI_PROCESSING,
    EMOJI_QUEUE,
    EMOJI_START,
    TerminalStepLogger,
    log_terminal,
)
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

# DynamoDB initialization is optional for local/dev.
dynamodb = resource(
    "dynamodb",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)

DDB_TABLE_NAME = os.getenv("DDB_TABLE", "").strip()
table = dynamodb.Table(DDB_TABLE_NAME) if DDB_TABLE_NAME else None


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _set_job_meta(job, **updates):
    if not job:
        return

    job.meta.update(updates)
    job.save_meta()


def _has_extracted_value(value):
    if value is None:
        return False

    text = str(value).strip()
    return bool(text) and text.lower() not in {
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
    }


def _is_empty_extraction(claim):
    claim = claim or {}
    patient = claim.get("patient") or {}
    insurance = claim.get("insurance") or {}
    payer = claim.get("payer") or {}

    if isinstance(payer, str):
        payer = {"name": payer}

    return (
        not _has_extracted_value(patient.get("name"))
        and not _has_extracted_value(insurance.get("member_id"))
        and not _has_extracted_value(payer.get("name"))
    )


def _hitl_reason(claim, default_reason):
    claim = claim or {}
    extraction_metadata = claim.get("extraction_metadata") or {}
    missing_fields = claim.get("missing_fields") or extraction_metadata.get("missing_fields") or []

    if missing_fields:
        return f"{default_reason}: missing {', '.join(missing_fields)}"

    return claim.get("reason") or default_reason


def _safe_progress(value, fallback=45):
    try:
        return max(int(float(value or 0)), fallback)
    except (TypeError, ValueError):
        return fallback


def _claim_confidence(claim):
    claim = claim or {}
    extraction = claim.get("extraction") or {}
    metadata = claim.get("extraction_metadata") or {}

    return (
        metadata.get("confidence")
        or claim.get("confidence")
        or claim.get("extraction_confidence")
        or extraction.get("confidence_score")
        or extraction.get("confidence")
        or extraction.get("extraction_confidence")
        or extraction.get("ocr_confidence")
    )


def _claim_submission_id(claim, fallback=None):
    claim = claim or {}

    candidates = [
        claim.get("submission_id"),
        (claim.get("submission") or {}).get("submission_id")
        if isinstance(claim.get("submission"), dict)
        else None,
        (claim.get("submission_payload") or {}).get("submission_id")
        if isinstance(claim.get("submission_payload"), dict)
        else None,
    ]

    for candidate in candidates:
        if candidate and str(candidate).startswith("SUB-"):
            return str(candidate)

    for candidate in candidates:
        if candidate:
            return str(candidate)

    return fallback


def _normalize_status(value):
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _deep_get(data, path, default=None):
    current = data

    for key in path.split("."):
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def _first_value(data, paths, default=None):
    for path in paths:
        value = _deep_get(data, path)

        if value not in (None, ""):
            return value

    return default


def _merge_dicts(*values):
    merged = {}

    for value in values:
        if isinstance(value, dict):
            merged.update(value)

    return merged


def _update_dynamo_job_status(sessionid, status, progress=None, error=None):
    if not table:
        return

    try:
        names = {"#s": "status"}
        values = {":s": status}
        updates = ["#s=:s"]

        if progress is not None:
            names["#p"] = "progress"
            values[":p"] = progress
            updates.append("#p=:p")

        if error:
            names["#e"] = "error"
            values[":e"] = str(error)
            updates.append("#e=:e")

        table.update_item(
            Key={"jobId": sessionid},
            UpdateExpression="SET " + ",".join(updates),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except Exception as update_error:
        logger.warning("DynamoDB job status update failed: %s", update_error)


async def _move_claim_to_hitl(claim, claim_id, reason):
    claim = claim or {}
    claim_id = claim_id if claim_id and claim_id != "UNKNOWN" else f"CLM-{uuid.uuid4().hex[:10]}"

    extraction = claim.get("extraction") or {}
    metadata = claim.get("extraction_metadata") or {}

    confidence = (
        metadata.get("confidence")
        or claim.get("extraction_confidence")
        or extraction.get("extraction_confidence")
        or 0
    )

    missing_fields = metadata.get("missing_fields") or claim.get("missing_fields") or []

    raw_fields_count = metadata.get("raw_fields_count")
    if raw_fields_count is None:
        raw_fields_count = len(claim.get("field_confidence") or [])

    extraction_metadata = {
        "confidence": confidence,
        "missing_fields": missing_fields,
        "raw_fields_count": raw_fields_count,
    }

    claim.update(
        {
            "claim_id": claim_id,
            "status": "HITL_REQUIRED",
            "review_status": "NEEDS_REVIEW",
            "review_state": "NEEDS_REVIEW",
            "queue_state": "HUMAN_REVIEW",
            "current_stage": "HUMAN_REVIEW",
            "current_step": "human_review_required",
            "active_step": "human_review_required",
            "current_agent": "HUMAN_REVIEW",
            "progress": _safe_progress(claim.get("progress")),
            "requires_human_review": True,
            "reason": reason,
            "extraction_metadata": extraction_metadata,
        }
    )

    save_claim(
        claim_id,
        "HITL_REQUIRED",
        "HUMAN_REVIEW",
        claim,
        total_charge=claim.get("total_charge", 0),
    )

    create_case(
        claim_id=claim_id,
        error=reason,
        case_type="HITL",
        metadata={
            "reason": reason,
            "extraction_metadata": extraction_metadata,
            "review_status": "NEEDS_REVIEW",
            "queue_state": "HUMAN_REVIEW",
        },
    )

    await emit_pipeline_event(
        "EXTRACTION",
        "HITL_REQUIRED",
        reason,
        claim_id=claim_id,
        submission_id=_claim_submission_id(claim, claim_id),
        metadata={
            "queue_state": "HUMAN_REVIEW",
            "review_status": "NEEDS_REVIEW",
            "review_state": "NEEDS_REVIEW",
            "current_stage": "HUMAN_REVIEW",
            "current_step": "human_review_required",
            "active_step": "human_review_required",
            "current_agent": "HUMAN_REVIEW",
            "progress": claim["progress"],
            "claim": claim,
            "extraction_metadata": extraction_metadata,
        },
    )

    await manager.broadcast(
        {
            "type": "manual_review_required",
            "event": "manual_review_required",
            "claim_id": claim_id,
            "status": "HITL_REQUIRED",
            "review_status": "NEEDS_REVIEW",
            "review_state": "NEEDS_REVIEW",
            "queue_state": "HUMAN_REVIEW",
            "current_stage": "HUMAN_REVIEW",
            "current_step": "human_review_required",
            "active_step": "human_review_required",
            "current_agent": "HUMAN_REVIEW",
            "progress": claim["progress"],
            "claim": claim,
        }
    )

    return {
        "claim_id": claim_id,
        "status": "HITL_REQUIRED",
        "review_status": "NEEDS_REVIEW",
        "queue_state": "HUMAN_REVIEW",
        "payload": claim,
        "validation": {
            "valid": False,
            "errors": [reason],
            "requires_human_review": True,
        },
    }


def process_document_job(
    bucket,
    key,
    processing_mode="MANUAL",
    upload_session_id="",
    temp_id="",
    claim_id="",
):
    terminal = TerminalStepLogger("process_document_job")

    terminal.log(
        f"Worker received document job: bucket={bucket}, key={key}",
        EMOJI_QUEUE,
    )
    print(f"📦 Worker received document job claim_id={claim_id}", flush=True)

    pipeline_log(
        "QUEUE",
        f"Job received from Redis Queue: bucket={bucket}, key={key}",
        status="QUEUE",
    )

    job = get_current_job()
    sessionid = upload_session_id or temp_id or (job.id if job else str(uuid.uuid4()))

    try:
        if table:
            table.put_item(
                Item={
                    "jobId": sessionid,
                    "status": "STARTED",
                    "progress": 0,
                    "bucket": bucket,
                    "key": key,
                    "claim_id": claim_id or "",
                    "processing_mode": processing_mode,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
            logger.info("Created DynamoDB job row: %s", sessionid)
        else:
            logger.debug("DynamoDB job tracking skipped because DDB_TABLE is not configured.")
    except Exception as create_error:
        logger.warning("Failed creating DynamoDB job row: %s", create_error)

    if job:
        terminal.log(f"RQ job started: job_id={job.id}", EMOJI_START)

    _set_job_meta(
        job,
        status="RUNNING",
        claim_id=claim_id,
        session_id=sessionid,
        bucket=bucket,
        key=key,
        processing_mode=processing_mode,
        steps={
            "s3_upload": "COMPLETED",
            "intake": "RUNNING",
        },
    )

    try:
        terminal.log("Claim processing started", EMOJI_PROCESSING)
        _update_dynamo_job_status(sessionid, "RUNNING", progress=10)

        result = asyncio.run(
            process_document_async(
                bucket,
                key,
                processing_mode=processing_mode,
                upload_session_id=upload_session_id,
                temp_id=temp_id,
                claim_id=claim_id,
            )
        )

        if isinstance(result, dict) and _normalize_status(result.get("status")) == "FAILED":
            error_message = result.get("error") or "Document job failed during intake"

            _update_dynamo_job_status(
                sessionid,
                "FAILED",
                progress=0,
                error=error_message,
            )

            _set_job_meta(
                job,
                status="FAILED",
                claim_id=claim_id,
                session_id=sessionid,
                steps={
                    **(job.meta.get("steps", {}) if job else {}),
                    "intake": "FAILED",
                },
                result=result,
                error=error_message,
            )

            terminal.log("Document job failed during intake", EMOJI_ERROR)
            return result

        _update_dynamo_job_status(sessionid, "COMPLETED", progress=100)

        _set_job_meta(
            job,
            status="COMPLETED",
            claim_id=claim_id,
            session_id=sessionid,
            steps={
                **(job.meta.get("steps", {}) if job else {}),
                "intake": "COMPLETED",
            },
            result=result,
        )

        terminal.completed("Document job completed successfully")
        return result

    except Exception as e:
        terminal.error("process_document_job", e)

        _update_dynamo_job_status(
            sessionid,
            "FAILED",
            error=str(e),
        )

        _set_job_meta(
            job,
            status="FAILED",
            claim_id=claim_id,
            session_id=sessionid,
            steps={
                **(job.meta.get("steps", {}) if job else {}),
                "intake": "FAILED",
            },
            error=str(e),
        )

        raise



def _is_clearinghouse_wait_result(result):
    """
    True when submission is complete but the claim must pause at Clearinghouse
    for manual approval/review.

    This checks the result, nested claim, and nested pipeline because different
    backend layers may place the same state in different keys.
    """
    if not isinstance(result, dict):
        return False

    claim = result.get("claim") if isinstance(result.get("claim"), dict) else {}
    pipeline = result.get("pipeline") if isinstance(result.get("pipeline"), dict) else {}

    status = _normalize_status(result.get("status"))
    stage = _normalize_status(result.get("stage") or result.get("current_stage"))
    pipeline_state = _normalize_status(result.get("pipeline_state") or result.get("pipeline_status"))
    active_step = _normalize_status(result.get("active_step") or result.get("current_step"))

    claim_status = _normalize_status(claim.get("status"))
    claim_stage = _normalize_status(claim.get("stage") or claim.get("current_stage"))
    claim_pipeline_state = _normalize_status(claim.get("pipeline_state") or claim.get("pipeline_status"))
    claim_active_step = _normalize_status(claim.get("active_step") or claim.get("current_step"))

    nested_pipeline_state = _normalize_status(
        pipeline.get("pipeline_state") or pipeline.get("pipeline_status")
    )
    nested_pipeline_stage = _normalize_status(
        pipeline.get("current_stage") or pipeline.get("stage") or pipeline.get("active_step")
    )

    clearinghouse_status = _normalize_status(
        result.get("clearinghouse_status")
        or claim.get("clearinghouse_status")
        or pipeline.get("clearinghouse_status")
    )

    wait_states = {
        "WAITING_FOR_APPROVAL",
        "PENDING_CLEARINGHOUSE",
        "PENDING_APPROVAL",
        "CLEARINGHOUSE_QUEUED",
        "QUEUED",
    }

    clearinghouse_stages = {
        "CLEARINGHOUSE",
        "CLEARINGHOUSE_REVIEW",
        "CLEARINGHOUSE_APPROVAL",
    }

    return (
        status in wait_states
        or pipeline_state in wait_states
        or claim_status in wait_states
        or claim_pipeline_state in wait_states
        or nested_pipeline_state in wait_states
        or clearinghouse_status in wait_states
        or clearinghouse_status == "PENDING_CLEARINGHOUSE"
        or stage in clearinghouse_stages
        or claim_stage in clearinghouse_stages
        or nested_pipeline_stage in clearinghouse_stages
        or active_step in clearinghouse_stages
        or claim_active_step in clearinghouse_stages
        or result.get("review_required") is True
        or result.get("approval_required") is True
        or claim.get("review_required") is True
        or claim.get("approval_required") is True
        or pipeline.get("review_required") is True
        or pipeline.get("approval_required") is True
    )


def _extract_pipeline_claim_from_result(result, original_claim):
    """
    Builds the latest claim object from the pipeline result without losing
    fields from the original queued claim.
    """
    if not isinstance(result, dict):
        return ensure_required_claim_aliases(original_claim or {})

    result_claim = result.get("claim") if isinstance(result.get("claim"), dict) else {}
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}

    claim = _merge_dicts(
        original_claim,
        payload,
        result_claim,
    )

    return ensure_required_claim_aliases(claim or {})


def _extract_pipeline_from_result(result, claim):
    """
    Builds the latest pipeline object from result.pipeline and claim.pipeline.
    """
    if not isinstance(result, dict):
        return claim.get("pipeline") if isinstance(claim, dict) else {}

    result_pipeline = result.get("pipeline") if isinstance(result.get("pipeline"), dict) else {}
    claim_pipeline = claim.get("pipeline") if isinstance(claim.get("pipeline"), dict) else {}

    return _merge_dicts(claim_pipeline, result_pipeline)


def _finalize_clearinghouse_wait_result(result, original_claim, claim_id):
    """
    Persists and broadcasts the correct paused state.

    Submission is complete, but manual mode means the claim must stop at
    Clearinghouse until approval. This prevents a generic later
    SUBMISSION/COMPLETED state from becoming the final UI state.
    """
    if not isinstance(result, dict):
        return result

    claim = _extract_pipeline_claim_from_result(result, original_claim)
    claim["claim_id"] = claim_id

    pipeline = _extract_pipeline_from_result(result, claim)

    submission_id = (
        result.get("submission_id")
        or claim.get("submission_id")
        or _claim_submission_id(claim, claim_id)
    )

    now = _utc_now_iso()

    steps = pipeline.get("steps") if isinstance(pipeline.get("steps"), dict) else {}
    steps.update(
        {
            "submission_done": True,
            "clearinghouse_queued": True,
            "clearinghouse_accepted": False,
            "acknowledged": False,
            "denial_checked": False,
            "paid": False,
            "learning_updated": False,
            "analytics_done": False,
        }
    )

    stage_status = pipeline.get("stage_status")
    if not isinstance(stage_status, dict):
        stage_status = {}

    stage_status.update(
        {
            "OCR": "COMPLETED",
            "VALIDATION": "COMPLETED",
            "COMPLIANCE": "COMPLETED",
            "SUBMISSION": "COMPLETED",
            "CLEARINGHOUSE": "PENDING",
            "DENIAL_AI": "PENDING",
            "PAYMENT": "PENDING",
            "LEARNING": "PENDING",
            "ANALYTICS": "PENDING",
        }
    )

    pipeline.update(
        {
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "pipeline_result": "WAITING_FOR_APPROVAL",
            "current_stage": "CLEARINGHOUSE",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "progress": 70,
            "review_required": True,
            "approval_required": True,
            "pipeline_paused": True,
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "submission_id": submission_id,
            "steps": steps,
            "stage_status": stage_status,
            "updated_at": now,
        }
    )

    claim.update(
        {
            "claim_id": claim_id,
            "submission_id": submission_id,
            "status": "PENDING_CLEARINGHOUSE",
            "stage": "CLEARINGHOUSE",
            "current_stage": "CLEARINGHOUSE",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "pipeline_result": "WAITING_FOR_APPROVAL",
            "review_required": True,
            "approval_required": True,
            "pipeline_paused": True,
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "progress": 70,
            "pipeline": pipeline,
            "updated_at": now,
        }
    )

    total_charge = claim.get("total_charge") or claim.get("amount") or 0

    save_claim(
        claim_id,
        "PENDING_CLEARINGHOUSE",
        "CLEARINGHOUSE",
        claim,
        total_charge=total_charge,
    )

    try:
        asyncio.run(
            emit_pipeline_event(
                "CLEARINGHOUSE",
                "WAITING_FOR_APPROVAL",
                "Claim is waiting for clearinghouse approval",
                claim_id=claim_id,
                submission_id=submission_id,
                metadata={
                    "claim": claim,
                    "pipeline": pipeline,
                    "current_stage": "CLEARINGHOUSE",
                    "current_agent": "CLEARINGHOUSE",
                    "active_step": "clearinghouse",
                    "pipeline_state": "WAITING_FOR_APPROVAL",
                    "clearinghouse_status": "PENDING_CLEARINGHOUSE",
                    "review_required": True,
                    "approval_required": True,
                    "progress": 70,
                },
            )
        )
    except Exception as event_error:
        logger.warning(
            "Failed emitting clearinghouse wait event for %s: %s",
            claim_id,
            event_error,
        )

    try:
        asyncio.run(
            manager.broadcast(
                {
                    "type": "agent_update",
                    "event": "agent_update",
                    "claim_id": claim_id,
                    "submission_id": submission_id,
                    "stage": "CLEARINGHOUSE",
                    "status": "WAITING_FOR_APPROVAL",
                    "progress": 70,
                    "current_stage": "CLEARINGHOUSE",
                    "current_agent": "CLEARINGHOUSE",
                    "active_step": "clearinghouse",
                    "pipeline_state": "WAITING_FOR_APPROVAL",
                    "pipeline_status": "WAITING_FOR_APPROVAL",
                    "clearinghouse_status": "PENDING_CLEARINGHOUSE",
                    "review_required": True,
                    "approval_required": True,
                    "pipeline_paused": True,
                    "claim": claim,
                    "pipeline": pipeline,
                    "timestamp": now,
                }
            )
        )
    except Exception as ws_error:
        logger.warning(
            "Failed broadcasting clearinghouse wait state for %s: %s",
            claim_id,
            ws_error,
        )

    result["claim"] = claim
    result["pipeline"] = pipeline
    result["status"] = "WAITING_FOR_APPROVAL"
    result["stage"] = "CLEARINGHOUSE"
    result["current_stage"] = "CLEARINGHOUSE"
    result["current_agent"] = "CLEARINGHOUSE"
    result["active_step"] = "clearinghouse"
    result["pipeline_state"] = "WAITING_FOR_APPROVAL"
    result["pipeline_status"] = "WAITING_FOR_APPROVAL"
    result["clearinghouse_status"] = "PENDING_CLEARINGHOUSE"
    result["review_required"] = True
    result["approval_required"] = True
    result["pipeline_paused"] = True
    result["progress"] = 70
    result["finalized_wait_state"] = True

    return result


def process_claim_job(claim, skip_validation=False):
    terminal = TerminalStepLogger("process_claim_job")
    claim = ensure_required_claim_aliases(claim or {})
    claim_id = claim.get("claim_id", "UNKNOWN")
    submission_id = _claim_submission_id(claim)

    pipeline_log(
        "QUEUE",
        "Job received from Redis Queue",
        claim_id=claim_id,
        submission_id=submission_id,
        status="QUEUE",
    )

    terminal.log(
        f"Worker received claim job: claim_id={claim_id}",
        EMOJI_QUEUE,
    )

    job = get_current_job()

    if job:
        terminal.log(f"RQ job started: job_id={job.id}", EMOJI_START)

    _set_job_meta(job, status="RUNNING", claim_id=claim_id, steps={})

    try:
        document_type = _normalize_status(
            claim.get("document_type")
            or claim.get("form_type")
            or claim.get("claim_type")
        )

        normalized_status = _normalize_status(
            claim.get("status")
            or claim.get("confidence_status")
            or claim.get("pipeline_status")
        )

        is_denial_ai_claim = (
            document_type == "EOB_ERA"
            or claim.get("denial_ai_required") is True
            or normalized_status == "DENIAL_AI_REQUIRED"
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
                    "progress": max(int(float(claim.get("progress") or 55)), 55),
                }
            )

            terminal.log("EOB/ERA denial claim routed to Denial AI", EMOJI_PROCESSING)

        missing = missing_required_fields_before_queue(claim)

        if missing and not is_denial_ai_claim:
            result = missing_fields_response(claim, missing)

            _set_job_meta(
                job,
                status="MISSING_FIELDS",
                claim_id=claim_id,
                result=result,
            )

            terminal.log(f"Claim missing required fields: {missing}", EMOJI_ERROR)
            return result

        if not is_denial_ai_claim and _is_empty_extraction(claim):
            reason = "Empty extraction"
            logger.warning("Empty extraction detected for claim %s", claim_id)

            result = asyncio.run(_move_claim_to_hitl(claim, claim_id, reason))

            _set_job_meta(
                job,
                status="HITL_REQUIRED",
                claim_id=claim_id,
                result=result,
            )

            terminal.log("Empty extraction routed to HITL", EMOJI_QUEUE)
            return result

        if not is_denial_ai_claim:
            confidence_status = claim_confidence_status(_claim_confidence(claim))

            if confidence_status:
                claim["confidence_status"] = confidence_status

                if confidence_status in {"AUTO_APPROVED", "VALIDATION_REQUIRED"}:
                    claim["status"] = confidence_status
                elif confidence_status == "HUMAN_REVIEW_REQUIRED":
                    claim["status"] = "HUMAN_REVIEW_REQUIRED"
                    claim["requires_human_review"] = True

        normalized_status = _normalize_status(claim.get("status"))

        if not is_denial_ai_claim and (
            claim.get("requires_human_review")
            or normalized_status in {
                "HITL_REQUIRED",
                "HUMAN_REVIEW_REQUIRED",
            }
        ):
            reason = _hitl_reason(claim, "Extraction requires human review")
            logger.warning("Extraction routed to HITL before pipeline: %s", reason)

            result = asyncio.run(_move_claim_to_hitl(claim, claim_id, reason))

            _set_job_meta(
                job,
                status="HITL_REQUIRED",
                claim_id=claim_id,
                result=result,
            )

            terminal.log("Extraction routed to HITL", EMOJI_QUEUE)
            return result

        terminal.log("Claim processing started", EMOJI_PROCESSING)

        result = asyncio.run(
            run_claim_pipeline(
                claim,
                job=job,
                skip_validation=skip_validation,
            )
        )

        if _is_clearinghouse_wait_result(result):
            result = _finalize_clearinghouse_wait_result(
                result,
                original_claim=claim,
                claim_id=claim_id,
            )

            _set_job_meta(
                job,
                status="WAITING_FOR_APPROVAL",
                claim_id=claim_id,
                submission_id=result.get("submission_id")
                or _claim_submission_id(result.get("claim"), claim_id),
                result=result,
                steps={
                    **(job.meta.get("steps", {}) if job else {}),
                    "pipeline": "PAUSED",
                    "submission": "COMPLETED",
                    "clearinghouse": "WAITING_FOR_APPROVAL",
                },
                completed_at=_utc_now_iso(),
            )

            terminal.log(
                "Claim paused at clearinghouse approval",
                EMOJI_QUEUE,
            )

            return result

        _set_job_meta(
            job,
            status="COMPLETED",
            claim_id=claim_id,
            result=result,
            steps={
                **(job.meta.get("steps", {}) if job else {}),
                "pipeline": "COMPLETED",
            },
            completed_at=_utc_now_iso(),
        )

        terminal.completed("Claim job completed successfully")
        return result

    except Exception as e:
        terminal.error("process_claim_job", e)

        _set_job_meta(
            job,
            status="FAILED",
            claim_id=claim_id,
            error=str(e),
            failed_at=_utc_now_iso(),
        )

        return {
            "status": "FAILED",
            "error": str(e),
            "claim_id": claim_id,
        }


def _extract_continuation_claim(result):
    if not isinstance(result, dict):
        return {}

    return _merge_dicts(
        result.get("claim"),
        _deep_get(result, "resumed.claim"),
        _deep_get(result, "queued.claim"),
        result.get("payload"),
    )


def _extract_continuation_pipeline(result, claim):
    if not isinstance(result, dict):
        return claim.get("pipeline") if isinstance(claim, dict) else {}

    pipeline = _first_value(
        result,
        [
            "pipeline",
            "resumed.pipeline",
            "resumed.claim.pipeline",
            "queued.pipeline",
            "queued.claim.pipeline",
            "claim.pipeline",
        ],
        {},
    )

    if not isinstance(pipeline, dict):
        pipeline = {}

    claim_pipeline = claim.get("pipeline") if isinstance(claim, dict) else {}

    return _merge_dicts(claim_pipeline, pipeline)


def _extract_payment_status(result, claim):
    raw_status = _first_value(
        {
            "result": result if isinstance(result, dict) else {},
            "claim": claim if isinstance(claim, dict) else {},
        },
        [
            # Prefer business reconciliation status first.
            "result.payment_status",
            "result.payment_result.payment_status",
            "result.payment.payment_status",
            "result.financials.payment_status",
            "result.financials.status",

            "result.resumed.claim.payment_status",
            "result.resumed.claim.payment_result.payment_status",
            "result.resumed.claim.payment.payment_status",
            "result.resumed.claim.financials.payment_status",
            "result.resumed.claim.financials.status",

            "result.claim.payment_status",
            "result.claim.payment_result.payment_status",
            "result.claim.payment.payment_status",
            "result.claim.financials.payment_status",
            "result.claim.financials.status",

            "claim.payment_status",
            "claim.payment_result.payment_status",
            "claim.payment.payment_status",
            "claim.financials.payment_status",
            "claim.financials.status",

            # Fallback only. ERA status may be PAID even for underpayment.
            "result.payment_result.status",
            "result.payment.status",
            "result.resumed.claim.payment_result.status",
            "result.resumed.claim.payment.status",
            "result.claim.payment_result.status",
            "result.claim.payment.status",
            "claim.payment_result.status",
            "claim.payment.status",
        ],
    )

    return _normalize_status(raw_status)


def _extract_paid_amount(result, claim):
    value = _first_value(
        {
            "result": result if isinstance(result, dict) else {},
            "claim": claim if isinstance(claim, dict) else {},
        },
        [
            "result.paid_amount",
            "result.payment_amount",
            "result.received_amount",
            "result.payment.paid_amount",
            "result.payment.received_amount",
            "result.payment_result.paid_amount",
            "result.resumed.claim.paid_amount",
            "result.resumed.claim.payment_amount",
            "result.claim.paid_amount",
            "claim.paid_amount",
            "claim.payment_amount",
            "claim.received_amount",
            "claim.payment.paid_amount",
            "claim.payment_result.paid_amount",
        ],
    )

    try:
        if value is None or value == "":
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def _looks_pipeline_finished(result, claim, pipeline):
    status = _normalize_status(
        _first_value(
            {
                "result": result if isinstance(result, dict) else {},
                "claim": claim,
                "pipeline": pipeline,
            },
            [
                "result.status",
                "result.pipeline_state",
                "result.pipeline_status",
                "claim.status",
                "claim.pipeline_state",
                "claim.pipeline_status",
                "pipeline.pipeline_state",
                "pipeline.pipeline_status",
                "pipeline.pipeline_result",
            ],
        )
    )

    stage = _normalize_status(
        _first_value(
            {
                "result": result if isinstance(result, dict) else {},
                "claim": claim,
                "pipeline": pipeline,
            },
            [
                "result.stage",
                "result.current_stage",
                "claim.stage",
                "claim.current_stage",
                "pipeline.current_stage",
                "pipeline.active_step",
            ],
        )
    )

    steps = pipeline.get("steps") if isinstance(pipeline, dict) else {}
    if not isinstance(steps, dict):
        steps = {}

    return (
        status in {"PAID", "COMPLETED", "COMPLETE", "SUCCESS", "FINISH", "APPROVED"}
        or stage in {"FINISH", "COMPLETED", "ANALYTICS"}
        or steps.get("analytics_done") is True
        or steps.get("paid") is True
    )


def _finalize_clearinghouse_continuation_result(result, claim_id, reviewer="SYSTEM"):
    """
    Persists final DB state after continue_after_accept() finishes.

    This prevents claims.payload from staying stuck at PROCESSING / ACKNOWLEDGMENT
    after Payment, Learning, and Analytics already completed in the worker.
    """
    if not isinstance(result, dict):
        return result

    if _normalize_status(result.get("status")) == "FAILED":
        return result

    claim = _extract_continuation_claim(result)
    claim = ensure_required_claim_aliases(claim or {})
    claim["claim_id"] = claim_id

    pipeline = _extract_continuation_pipeline(result, claim)
    payment_status = _extract_payment_status(result, claim)
    paid_amount = _extract_paid_amount(result, claim)

    result_status = _normalize_status(result.get("status"))
    result_stage = _normalize_status(result.get("stage"))
    pipeline_finished = _looks_pipeline_finished(result, claim, pipeline)

    if payment_status in {
        "UNDERPAID",
        "OVERPAID",
        "PAID_WITH_ADJUSTMENT",
        "PAYMENT_RECONCILIATION_REQUIRED",
    }:
        final_status = "PAYMENT_RECONCILIATION_REQUIRED"
        final_stage = "FINISH"
        final_agent = "AnalyticsAgent"
        final_current_stage = "ANALYTICS"
        final_pipeline_state = "PAYMENT_RECONCILIATION_REQUIRED"
        final_pipeline_result = "PAYMENT_RECONCILIATION_REQUIRED"
        final_payment_status = payment_status

    elif payment_status in {"DENIED", "PAYMENT_DENIED"}:
        final_status = "PAYMENT_DENIED"
        final_stage = "FINISH"
        final_agent = "AnalyticsAgent"
        final_current_stage = "ANALYTICS"
        final_pipeline_state = "PAYMENT_DENIED"
        final_pipeline_result = "PAYMENT_DENIED"
        final_payment_status = payment_status

    elif payment_status in {"PAID", "SUCCESS", "APPROVED"}:
        final_status = "PAID"
        final_stage = "FINISH"
        final_agent = "AnalyticsAgent"
        final_current_stage = "ANALYTICS"
        final_pipeline_state = "COMPLETED"
        final_pipeline_result = "COMPLETED"
        final_payment_status = "PAID"

    elif paid_amount is not None:
        final_status = claim.get("status") or result.get("status") or "COMPLETED"
        final_stage = claim.get("stage") or result.get("stage") or "FINISH"
        final_agent = "AnalyticsAgent"
        final_current_stage = "ANALYTICS"
        final_pipeline_state = claim.get("pipeline_state") or result.get("pipeline_state") or "COMPLETED"
        final_pipeline_result = claim.get("pipeline_result") or result.get("pipeline_result") or final_pipeline_state
        final_payment_status = payment_status or claim.get("payment_status")

    elif result_status in {
        "DENIED",
        "REJECTED",
        "HARD_REJECT",
        "HARD_REJECTED",
        "FAILED",
        "ERROR",
    }:
        final_status = result_status
        final_stage = result_stage or "DENIAL"
        final_agent = claim.get("current_agent") or "DENIAL_AI"
        final_current_stage = claim.get("current_stage") or final_stage
        final_pipeline_state = result_status
        final_pipeline_result = result_status
        final_payment_status = claim.get("payment_status")
    elif pipeline_finished:
        final_status = "COMPLETED"
        final_stage = "FINISH"
        final_agent = "AnalyticsAgent"
        final_current_stage = "ANALYTICS"
        final_pipeline_state = "COMPLETED"
        final_pipeline_result = "COMPLETED"
        final_payment_status = claim.get("payment_status")
    else:
        final_status = claim.get("status") or result.get("status") or "PROCESSING"
        final_stage = claim.get("stage") or result.get("stage") or "ACKNOWLEDGMENT"
        final_agent = claim.get("current_agent") or result.get("current_agent") or "PAYER_ACKNOWLEDGMENT"
        final_current_stage = claim.get("current_stage") or result.get("current_stage") or final_stage
        final_pipeline_state = claim.get("pipeline_state") or result.get("pipeline_state") or "PROCESSING"
        final_pipeline_result = claim.get("pipeline_result") or result.get("pipeline_result")
        final_payment_status = claim.get("payment_status")

    steps = pipeline.get("steps") if isinstance(pipeline.get("steps"), dict) else {}

    if final_status in {
        "PAID",
        "COMPLETED",
        "PAYMENT_RECONCILIATION_REQUIRED",
        "PAYMENT_DENIED",
    }:
        steps.update(
            {
                "clearinghouse_accepted": True,
                "clearinghouse_queued": False,
                "acknowledged": True,
                "denial_checked": True,
                "paid": final_status == "PAID",
                "payment_reconciliation_required": final_status == "PAYMENT_RECONCILIATION_REQUIRED",
                "payment_denied": final_status == "PAYMENT_DENIED",
                "learning_updated": True,
                "analytics_done": True,
            }
        )

        stage_status = pipeline.get("stage_status")
        if not isinstance(stage_status, dict):
            stage_status = {}

        stage_status.update(
            {
                "OCR": "COMPLETED",
                "VALIDATION": "COMPLETED",
                "COMPLIANCE": "COMPLETED",
                "SUBMISSION": "COMPLETED",
                "CLEARINGHOUSE": "COMPLETED",
                "DENIAL_AI": "COMPLETED",
                "PAYMENT": (
                    "COMPLETED"
                    if final_status in {
                        "PAID",
                        "PAYMENT_RECONCILIATION_REQUIRED",
                        "PAYMENT_DENIED",
                    }
                    else stage_status.get("PAYMENT", "PENDING")
                ),
                "LEARNING": "COMPLETED",
                "ANALYTICS": "COMPLETED",
            }
        )

        pipeline["stage_status"] = stage_status

    pipeline.update(
        {
            "pipeline_state": final_pipeline_state,
            "pipeline_status": final_pipeline_state,
            "pipeline_result": final_pipeline_result,
            "current_stage": final_current_stage,
            "current_agent": final_agent,
            "active_step": "completed" if final_stage == "FINISH" else str(final_stage).lower(),
            "progress": 100 if final_stage == "FINISH" else claim.get("progress", 70),
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "steps": steps,
            "updated_at": _utc_now_iso(),
        }
    )

    claim.update(
        {
            "claim_id": claim_id,
            "status": final_status,
            "stage": final_stage,
            "current_stage": final_current_stage,
            "current_agent": final_agent,
            "active_step": pipeline.get("active_step"),
            "pipeline_state": final_pipeline_state,
            "pipeline_status": final_pipeline_state,
            "pipeline_result": final_pipeline_result,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "clearinghouse_accepted": True,
            "clearinghouse_approved": True,
            "payment_status": final_payment_status,
            "progress": 100 if final_stage == "FINISH" else claim.get("progress", 70),
            "pipeline": pipeline,
            "updated_at": _utc_now_iso(),
            "resumed_by": reviewer,
        }
    )

    if paid_amount is not None:
        claim["paid_amount"] = paid_amount
        claim["payment_amount"] = paid_amount
        claim["received_amount"] = paid_amount

    if isinstance(result.get("payment"), dict):
        claim["payment"] = result["payment"]

    if isinstance(result.get("analytics"), dict):
        claim["analytics"] = result["analytics"]

    total_charge = claim.get("total_charge") or claim.get("amount") or 0

    save_claim(
        claim_id,
        final_status,
        final_stage,
        claim,
        total_charge=total_charge,
    )

    try:
        asyncio.run(
            emit_pipeline_event(
                final_current_stage,
                final_status,
                f"Clearinghouse continuation finalized as {final_status}",
                claim_id=claim_id,
                submission_id=_claim_submission_id(claim, claim_id),
                metadata={
                    "claim": claim,
                    "pipeline": pipeline,
                    "current_stage": final_current_stage,
                    "current_agent": final_agent,
                    "pipeline_state": final_pipeline_state,
                    "payment_status": final_payment_status,
                    "progress": claim.get("progress"),
                },
            )
        )
    except Exception as event_error:
        logger.warning(
            "Failed emitting final clearinghouse continuation event for %s: %s",
            claim_id,
            event_error,
        )

    final_progress = claim.get("progress") or (100 if final_stage == "FINISH" else 70)

    try:
        asyncio.run(
            manager.broadcast(
                {
                    "type": "agent_update",
                    "event": "agent_update",
                    "claim_id": claim_id,
                    "stage": final_current_stage,
                    "status": final_status,
                    "progress": final_progress,
                    "current_stage": final_current_stage,
                    "current_agent": final_agent,
                    "active_step": pipeline.get("active_step"),
                    "pipeline_state": final_pipeline_state,
                    "pipeline_status": final_pipeline_state,
                    "pipeline_result": final_pipeline_result,
                    "payment_status": final_payment_status,
                    "review_required": False,
                    "approval_required": False,
                    "pipeline_paused": False,
                    "claim": {
                        **claim,
                        "status": final_status,
                        "stage": final_stage,
                        "current_stage": final_current_stage,
                        "current_agent": final_agent,
                        "active_step": pipeline.get("active_step"),
                        "pipeline_state": final_pipeline_state,
                        "pipeline_status": final_pipeline_state,
                        "pipeline_result": final_pipeline_result,
                        "payment_status": final_payment_status,
                        "progress": final_progress,
                        "review_required": False,
                        "approval_required": False,
                        "pipeline_paused": False,
                    },
                    "pipeline": {
                        **pipeline,
                        "pipeline_state": final_pipeline_state,
                        "pipeline_status": final_pipeline_state,
                        "pipeline_result": final_pipeline_result,
                        "current_stage": final_current_stage,
                        "current_agent": final_agent,
                        "active_step": pipeline.get("active_step"),
                        "progress": final_progress,
                        "review_required": False,
                        "approval_required": False,
                        "pipeline_paused": False,
                    },
                    "timestamp": _utc_now_iso(),
                }
            )
        )
    except Exception as ws_error:
        logger.warning(
            "Failed broadcasting final clearinghouse continuation state for %s: %s",
            claim_id,
            ws_error,
        )

    result["claim"] = claim
    result["pipeline"] = pipeline
    result["status"] = final_status
    result["stage"] = final_stage
    result["pipeline_state"] = final_pipeline_state
    result["payment_status"] = final_payment_status
    result["finalized"] = True

    return result


def continue_clearinghouse_pipeline_job(claim_id, reviewer="SYSTEM"):
    terminal = TerminalStepLogger("continue_clearinghouse_pipeline_job")
    job = get_current_job()

    _set_job_meta(
        job,
        status="RUNNING",
        claim_id=claim_id,
        reviewer=reviewer,
        started_at=_utc_now_iso(),
    )

    try:
        from app.db.database import SessionLocal
        from app.services.clearinghouse_orchestration_service import (
            ClearinghouseOrchestrationService,
        )

        db = SessionLocal()

        try:
            terminal.log(
                f"Continuing clearinghouse pipeline: claim_id={claim_id}",
                EMOJI_PROCESSING,
            )

            result = asyncio.run(
                ClearinghouseOrchestrationService(db).continue_after_accept(
                    claim_id,
                    reviewer=reviewer,
                )
            )

            result = _finalize_clearinghouse_continuation_result(
                result,
                claim_id=claim_id,
                reviewer=reviewer,
            )

            _set_job_meta(
                job,
                status="COMPLETED",
                claim_id=claim_id,
                result=result,
                completed_at=_utc_now_iso(),
            )

            terminal.completed("Clearinghouse continuation completed")
            return result

        finally:
            db.close()

    except Exception as e:
        terminal.error("continue_clearinghouse_pipeline_job", e)

        _set_job_meta(
            job,
            status="FAILED",
            claim_id=claim_id,
            error=str(e),
            failed_at=_utc_now_iso(),
        )

        return {
            "status": "FAILED",
            "error": str(e),
            "claim_id": claim_id,
        }


def process_claim_chunk_job(claims, bulk_session_id="", chunk_index=0, total_chunks=1):
    terminal = TerminalStepLogger("process_claim_chunk_job")

    terminal.log(
        f"Worker received bulk chunk: session={bulk_session_id}, "
        f"chunk={chunk_index + 1}/{total_chunks}, claims={len(claims)}",
        EMOJI_QUEUE,
    )

    job = get_current_job()

    _set_job_meta(
        job,
        status="RUNNING",
        bulk_session_id=bulk_session_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        total_claims=len(claims),
    )

    try:
        result = asyncio.run(
            process_claim_chunk_async(
                claims,
                bulk_session_id=bulk_session_id,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
            )
        )

        _set_job_meta(job, status="COMPLETED", result=result)
        terminal.completed("Bulk chunk job completed successfully")
        return result

    except Exception as e:
        terminal.error("process_claim_chunk_job", e)

        _set_job_meta(job, status="FAILED", error=str(e))

        return {
            "status": "FAILED",
            "error": str(e),
            "bulk_session_id": bulk_session_id,
        }


def send_to_dlq(data):
    from app.queue.queue_manager import dlq_queue

    log_terminal("Queueing failed payload to DLQ", EMOJI_QUEUE)
    dlq_queue.enqueue("app.queue.jobs.store_dlq", data)


def store_dlq(data):
    log_terminal(f"Stored in DLQ: {data}", EMOJI_ERROR)
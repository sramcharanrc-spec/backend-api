import asyncio
import copy
import logging
from datetime import datetime

from app.agents.analytics.analytics_agent import AnalyticsAgent
from app.agents.compliance.compliance_agent import ComplianceAgent
from app.agents.eligibility.eligibility_agent import EligibilityAgent
from app.agents.learning.learning_agent import LearningAgent
from app.agents.ai_suggestions.claim_repair_engine import ClaimRepairEngine
from app.agents.denial_ai.llm_denial_agent import LLMDenialAgent
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.validation.validation_agent import ValidationAgent
from app.intake.db_service import save_record, update_case
from app.orchestrator.case_orchestrator import build_case_record
from app.rcm.claim_store import save_claim
from app.rcm.agentic_ai import predict_denial
from app.rcm.edi_responses import generate_277ca, generate_999_ack, generate_era_835
from app.rcm.pipeline_observability import emit_pipeline_event, pipeline_log
from app.services.enterprise_observability_service import (
    CONFIDENCE_THRESHOLD,
    detect_form_type_from_payload,
    hitl_reasons_for_claim,
)
from app.utils.confidence import claim_confidence_status
from app.utils.event_deduplicator import emit_once_async
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

_PIPELINE_SAVE_CACHE = {}
_PIPELINE_SAVE_DEDUPE_SECONDS = 8
_PENDING_SAVE_TASKS = {}

PIPELINE_STATES = [
    "OCR_COMPLETED",
    "VALIDATION_COMPLETED",
    "COMPLIANCE_COMPLETED",
    "WAITING_FOR_REVIEW",
    "CLEARINGHOUSE_PENDING",
    "CLEARINGHOUSE_SUBMITTED",
    "WAITING_FOR_APPROVAL",
    "ACK_RECEIVED",
    "PAYER_PENDING",
    "DENIAL_ANALYSIS",
    "ANALYTICS_COMPLETED",
    "APPROVED",
    "HUMAN_REVIEW_REQUIRED",
    "HITL_REQUIRED",
    "HARD_REJECT",
]

STAGE_ORDER = {
    "extract": 1,
    "validation": 2,
    "compliance": 3,
    "waiting_for_review": 4,
    "submission": 5,
    "clearinghouse": 6,
    "payer": 7,
    "denial_ai": 8,
    "payment": 9,
    "learning": 10,
    "analytics": 11,
    "completed": 12,
}

AGENT_BY_STEP = {
    "extract": "OCR / Extraction",
    "validation": "Validation",
    "compliance": "Compliance",
    "waiting_for_review": "SUBMISSION_REVIEW",
    "submission": "Submission Review",
    "clearinghouse": "Clearinghouse",
    "payer": "Payer",
    "denial_ai": "Denial AI",
    "payment": "Payment",
    "learning": "Learning",
    "analytics": "Analytics",
    "completed": "NONE",
}

PROGRESS_BY_STEP = {
    ("validation", "COMPLETED"): 40,
    ("compliance", "COMPLETED"): 60,
    ("submission", "RUNNING"): 62,
    ("submission", "COMPLETED"): 65,
    ("clearinghouse", "WAITING_FOR_APPROVAL"): 70,
    ("clearinghouse", "COMPLETED"): 75,
    ("denial_ai", "COMPLETED"): 80,
    ("payment", "RUNNING"): 82,
    ("payment", "COMPLETED"): 85,
    ("learning", "RUNNING"): 90,
    ("learning", "COMPLETED"): 92,
    ("analytics", "RUNNING"): 95,
    ("analytics", "COMPLETED"): 98,
    ("completed", "COMPLETED"): 100,
}

FINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "REJECTED",
    "ACCEPTED",
    "HITL_REQUIRED",
    "HUMAN_REVIEW_REQUIRED",
    "HARD_REJECT",
    "WAITING_FOR_REVIEW",
    "PENDING_APPROVAL",
    "PENDING_CLEARINGHOUSE",
}


def _claim_submission_id(claim: dict, fallback=None) -> str:
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

    return str(fallback or claim.get("claim_id") or "")


def _sync_submission_id(claim: dict) -> str:
    submission_id = _claim_submission_id(claim)

    if submission_id and submission_id.startswith("SUB-"):
        claim["submission_id"] = submission_id

        if isinstance(claim.get("submission"), dict):
            claim["submission"]["submission_id"] = submission_id

        if isinstance(claim.get("submission_payload"), dict):
            claim["submission_payload"]["submission_id"] = submission_id

    return submission_id


def _normalize_status(value):
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _utc_now():
    return datetime.utcnow().isoformat()


def _as_percent_value(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return round(number * 100, 3) if 0 < number <= 1 else round(number, 3)


def _apply_quality_metrics(claim, validation):
    extraction = claim.get("extraction") or {}
    validation_score = validation.get("validation_score", validation.get("score", claim.get("validation_score")))
    ocr_confidence = (
        validation.get("ocr_confidence")
        or claim.get("ocr_confidence")
        or extraction.get("ocr_confidence")
        or extraction.get("ocr_quality")
        or extraction.get("extraction_confidence")
        or claim.get("confidence")
        or validation_score
    )
    ai_confidence = validation.get("ai_confidence")
    if ai_confidence in (None, "", 0, 0.0):
        ai_confidence = claim.get("ai_confidence") or claim.get("confidence") or validation_score or 0
    completeness_score = (
        validation.get("completeness_score")
        or claim.get("completeness_score")
        or extraction.get("completeness_score")
        or extraction.get("completeness")
        or validation_score
    )
    claim["validation_score"] = validation_score
    claim["ocr_confidence"] = ocr_confidence
    claim["ai_confidence"] = ai_confidence
    claim["completeness_score"] = completeness_score
    return claim


def _set_pipeline_state(claim, pipeline, state, step, status, completed=False, metadata=None):
    now = _utc_now()
    step = str(step or "").lower()
    status = _normalize_status(status) or status

    claim["pipeline_state"] = state
    claim["pipeline_status"] = status
    claim["current_stage"] = step.upper()
    claim["active_step"] = step
    claim["current_agent"] = AGENT_BY_STEP.get(step, step.replace("_", " ").title())
    claim["updated_at"] = now

    if state in PIPELINE_STATES:
        if status in {"WAITING_FOR_APPROVAL", "HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "HARD_REJECT"}:
            claim["status"] = state
        else:
            claim["status"] = claim.get("status", state)

    pipeline.setdefault("steps", {})
    pipeline["active_step"] = step
    pipeline["current_stage"] = claim["current_stage"]
    pipeline["current_agent"] = claim["current_agent"]
    pipeline["pipeline_state"] = state
    pipeline["pipeline_status"] = status
    pipeline["stage_order"] = STAGE_ORDER.get(step, 0)
    pipeline["event_version"] = int(pipeline.get("event_version") or 0) + 1

    progress = PROGRESS_BY_STEP.get((step, status))
    if progress is not None:
        claim["progress"] = progress
        pipeline["progress"] = progress

    history = claim.setdefault("stage_history", [])
    current = next(
        (entry for entry in reversed(history) if entry.get("stage") == step and not entry.get("completed_at")),
        None,
    )
    if current is None:
        current = {
            "stage": step,
            "state": state,
            "status": status,
            "started_at": now,
            "metadata": metadata or {},
        }
        history.append(current)
    else:
        current["state"] = state
        current["status"] = status
        current["metadata"] = {**(current.get("metadata") or {}), **(metadata or {})}

    if completed or status in {"COMPLETED", "SUCCESS", "APPROVED", "HITL_REQUIRED", "HARD_REJECT"}:
        current.setdefault("completed_at", now)
        try:
            started = datetime.fromisoformat(str(current["started_at"]))
            finished = datetime.fromisoformat(str(current["completed_at"]))
            current["duration_seconds"] = round((finished - started).total_seconds(), 3)
        except (TypeError, ValueError):
            current["duration_seconds"] = 0

    if completed:
        completed_stages = set(claim.get("completed_stages") or [])
        completed_stages.add(step)
        claim["completed_stages"] = sorted(completed_stages, key=lambda value: STAGE_ORDER.get(value, 999))
        pipeline["completed_stages"] = claim["completed_stages"]

    return claim


async def _broadcast_realtime_stage(claim, pipeline, event_name, status, message, metadata=None):
    step = str(claim.get("active_step") or "").lower()
    payload = {
        "type": "agent_update",
        "event": "agent_update",
        "claim_id": claim.get("claim_id"),
        "stage": claim.get("current_stage"),
        "status": status,
        "progress": claim.get("progress"),
        "current_stage": claim.get("current_stage"),
        "current_agent": claim.get("current_agent"),
        "active_step": step,
        "pipeline_state": claim.get("pipeline_state"),
        "claim": claim,
        "timestamp": _utc_now(),
    }
    await manager.broadcast(payload)
    await emit_pipeline_event(
        claim.get("current_agent") or step or "PIPELINE",
        status,
        message,
        claim_id=claim.get("claim_id"),
        submission_id=_claim_submission_id(claim, fallback=claim.get("claim_id")),
        metadata={
            "current_stage": claim.get("current_stage"),
            "current_agent": claim.get("current_agent"),
            "active_step": step,
            "pipeline_state": claim.get("pipeline_state"),
            "progress": claim.get("progress"),
            **(metadata or {}),
        },
    )


async def _emit_stage_state(agent, status, message, claim, pipeline, metadata=None):
    step = str(claim.get("active_step") or agent).lower()
    await emit_pipeline_event(
        agent,
        status,
        message,
        claim_id=claim.get("claim_id"),
        submission_id=_claim_submission_id(claim, fallback=claim.get("claim_id")),
        metadata={
            "event_version": pipeline.get("event_version"),
            "stage_order": pipeline.get("stage_order"),
            "pipeline_state": claim.get("pipeline_state"),
            "pipeline_status": claim.get("pipeline_status"),
            "current_agent": claim.get("current_agent"),
            "current_stage": claim.get("current_stage"),
            "active_step": step,
            "completed_stages": claim.get("completed_stages", []),
            "stage_history": claim.get("stage_history", []),
            **(metadata or {}),
        },
    )


async def _broadcast_claim_available(claim, pipeline, status="CLAIM_AVAILABLE"):
    await manager.broadcast({
        "type": "CLAIM_AVAILABLE",
        "event": "CLAIM_AVAILABLE",
        "claim_id": claim.get("claim_id"),
        "temp_id": claim.get("temp_id"),
        "upload_session_id": claim.get("upload_session_id"),
        "status": status,
        "stage": claim.get("current_stage"),
        "step": claim.get("active_step"),
        "current_agent": claim.get("current_agent"),
        "current_stage": claim.get("current_stage"),
        "pipeline_state": claim.get("pipeline_state"),
        "pipeline_status": claim.get("pipeline_status"),
        "progress": claim.get("progress") or pipeline.get("progress"),
        "claim": claim,
        "timestamp": _utc_now(),
    })


async def _return_terminal_state(
    mapped_claim,
    status,
    pipeline,
    validation=None,
    case=None,
    clearinghouse=None,
    denial=None,
    payment=None,
    message=None,
):
    claim_id = mapped_claim.get("claim_id")
    submission_id = _claim_submission_id(mapped_claim, fallback=claim_id)
    final_status = _normalize_status(status)

    if final_status in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"}:
        mapped_claim["status"] = final_status
        mapped_claim["pipeline_state"] = final_status
        mapped_claim["pipeline_status"] = final_status
        mapped_claim["review_required"] = True
        mapped_claim["approval_required"] = True
        mapped_claim["pipeline_paused"] = True
        mapped_claim["waiting_for_human"] = True

        if case:
            mapped_claim["case"] = case
            mapped_claim["case_id"] = case.get("case_id")
            mapped_claim["hitl_case"] = case

            pipeline["case"] = case
            pipeline["case_id"] = case.get("case_id")

        pipeline["pipeline_state"] = final_status
        pipeline["pipeline_status"] = final_status
        pipeline["review_required"] = True
        pipeline["approval_required"] = True
        pipeline["pipeline_paused"] = True
        pipeline["waiting_for_human"] = True

    pipeline_log(
        "PIPELINE",
        message or f"Pipeline stopped with terminal status {final_status}",
        claim_id=claim_id,
        submission_id=submission_id,
        status="STOP" if final_status != "COMPLETED" else "SUCCESS",
    )


def _mark_step(job, step, status):
    if not job:
        return
    job.meta.setdefault("steps", {})
    job.meta["steps"][step] = status
    job.save_meta()


def _save_trace_id(job, trace_id):
    if not job or not trace_id:
        return
    job.meta["trace_id"] = trace_id
    job.save_meta()


def _pipeline_steps(**overrides):
    steps = {
        "eligibility_checked": False,
        "case_orchestrated": False,
        "rules_validated": False,
        "compliance_checked": False,
        "edi_generation": False,
        "submitted": False,
        "clearinghouse_queued": False,
        "acknowledged": False,
        "denial_checked": False,
        "paid": False,
        "learning_updated": False,
        "analytics_done": False,
    }
    steps.update(overrides)
    return {"steps": steps}


def _build_pipeline_record(
    claim,
    status,
    pipeline,
    validation=None,
    case=None,
    clearinghouse=None,
    denial=None,
    payment=None,
):
    return {
        "claim_id": claim.get("claim_id"),
        "status": status,
        "pipeline_state": claim.get("pipeline_state") or status,
        "pipeline_status": claim.get("pipeline_status") or status,
        "current_agent": claim.get("current_agent"),
        "current_stage": claim.get("current_stage"),
        "active_step": claim.get("active_step"),
        "queue_state": claim.get("queue_state"),
        "pipeline_paused": claim.get("pipeline_paused", False),
        "waiting_for_human": claim.get("waiting_for_human", False),
        "review_required": claim.get("review_required", False),
        "approval_required": claim.get("approval_required", False),
        "review_status": claim.get("review_status"),
        "clearinghouse_status": claim.get("clearinghouse_status"),
        "submission_id": _claim_submission_id(claim, fallback=claim.get("claim_id")),
        "submission_started": claim.get("submission_started"),
        "submission_status": claim.get("submission_status"),
        "progress": claim.get("progress"),
        "completed_stages": claim.get("completed_stages", []),
        "stage_history": claim.get("stage_history", []),
        "agents": claim.get("agents", {}),
        "claim": claim,
        "pipeline": pipeline,
        "validation": validation or {},
        "case": case,
        "clearinghouse": clearinghouse,
        "denial": denial,
        "payment": payment,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _pipeline_save_key(claim, status):
    claim = claim or {}
    claim_id = str(claim.get("claim_id") or "").strip()
    pipeline_state = _normalize_status(claim.get("pipeline_state") or status or claim.get("status"))
    current_stage = _normalize_status(claim.get("current_stage") or claim.get("stage"))
    active_step = str(claim.get("active_step") or "").strip().lower()
    save_status = _normalize_status(status or claim.get("status") or pipeline_state)

    if save_status == "HARD_REJECT" or pipeline_state == "HARD_REJECT":
        pipeline_state = "HARD_REJECT"
        current_stage = "COMPLIANCE"
        active_step = "compliance"
        save_status = "HARD_REJECT"

    if save_status in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"}:
        pipeline_state = save_status
        current_stage = current_stage or "WAITING_FOR_REVIEW"
        active_step = active_step or "waiting_for_review"

    if save_status in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE"}:
        pipeline_state = "WAITING_FOR_APPROVAL"
        current_stage = "CLEARINGHOUSE"
        active_step = "clearinghouse"
        save_status = "WAITING_FOR_APPROVAL"

    if save_status in {"PAID", "COMPLETED"}:
        pipeline_state = "COMPLETED"
        current_stage = "COMPLETED"
        active_step = "completed"

    return f"{claim_id}:{pipeline_state}:{current_stage}:{active_step}:{save_status}"


def _save_pipeline_record(
    claim,
    status,
    pipeline,
    validation=None,
    case=None,
    clearinghouse=None,
    denial=None,
    payment=None,
):
    record = _build_pipeline_record(
        claim,
        status,
        pipeline,
        validation=validation,
        case=case,
        clearinghouse=clearinghouse,
        denial=denial,
        payment=payment,
    )

    claim_id = claim.get("claim_id")
    submission_id = _claim_submission_id(claim, fallback=claim_id)

    try:
        pipeline_log(
            "DB_AGENT",
            "Saving claim to PostgreSQL",
            claim_id=claim_id,
            submission_id=submission_id,
            status="DB",
        )
        save_record(record)
        pipeline_log(
            "DB_AGENT",
            "Claim saved successfully",
            claim_id=claim_id,
            submission_id=submission_id,
            status="SUCCESS",
        )
        return record
    except Exception as error:
        pipeline_log(
            "DB_AGENT",
            f"Claim save failed: {str(error)}",
            claim_id=claim_id,
            submission_id=submission_id,
            status="ERROR",
        )
        logger.exception("Pipeline record save failed")
        raise


def _schedule_pipeline_record_save(
    claim,
    status,
    pipeline,
    validation=None,
    case=None,
    clearinghouse=None,
    denial=None,
    payment=None,
):
    save_key = _pipeline_save_key(claim, status)
    now = datetime.utcnow().timestamp()

    existing_task = _PENDING_SAVE_TASKS.get(save_key)
    if existing_task and hasattr(existing_task, "done") and not existing_task.done():
        print(f"[DB_AGENT] Save already pending, skipping: {save_key}")
        return existing_task

    last_saved = _PIPELINE_SAVE_CACHE.get(save_key)
    if last_saved and now - last_saved < _PIPELINE_SAVE_DEDUPE_SECONDS:
        print(f"[DB_AGENT] Skipping duplicate pipeline save: {save_key}")
        return None

    _PIPELINE_SAVE_CACHE[save_key] = now

    claim_snapshot = copy.deepcopy(claim)
    pipeline_snapshot = copy.deepcopy(pipeline)
    validation_snapshot = copy.deepcopy(validation)
    case_snapshot = copy.deepcopy(case)
    clearinghouse_snapshot = copy.deepcopy(clearinghouse)
    denial_snapshot = copy.deepcopy(denial)
    payment_snapshot = copy.deepcopy(payment)

    try:
        loop = asyncio.get_running_loop()

        async def save_task():
            try:
                return await asyncio.to_thread(
                    _save_pipeline_record,
                    claim_snapshot,
                    status,
                    pipeline_snapshot,
                    validation_snapshot,
                    case_snapshot,
                    clearinghouse_snapshot,
                    denial_snapshot,
                    payment_snapshot,
                )
            finally:
                _PENDING_SAVE_TASKS.pop(save_key, None)

        task = loop.create_task(save_task())
        _PENDING_SAVE_TASKS[save_key] = task
        return task
    except RuntimeError:
        try:
            _PENDING_SAVE_TASKS[save_key] = True
            return _save_pipeline_record(
                claim_snapshot,
                status,
                pipeline_snapshot,
                validation=validation_snapshot,
                case=case_snapshot,
                clearinghouse=clearinghouse_snapshot,
                denial=denial_snapshot,
                payment=payment_snapshot,
            )
        finally:
            _PENDING_SAVE_TASKS.pop(save_key, None)


async def _emit_agent_update(claim, stage, status, progress=None, pipeline_state=None):
    claim = claim or {}

    stage_upper = str(stage or claim.get("current_stage") or claim.get("stage") or "PIPELINE").upper()
    status_upper = str(status or claim.get("status") or "RUNNING").upper()

    step_map = {
        "OCR": "ocr",
        "EXTRACTION": "extraction",
        "ELIGIBILITY": "eligibility",
        "VALIDATION": "validation",
        "COMPLIANCE": "compliance",
        "SUBMISSION": "submission",
        "CLEARINGHOUSE": "clearinghouse",
        "ACKNOWLEDGMENT": "acknowledgment",
        "PAYER_ACKNOWLEDGMENT": "acknowledgment",
        "DENIAL": "denial_ai",
        "DENIAL_AI": "denial_ai",
        "PAYMENT": "payment",
        "LEARNING": "learning",
        "ANALYTICS": "analytics",
        "FINISH": "completed",
        "COMPLETED": "completed",
    }

    running_progress = {
        "OCR": 10,
        "EXTRACTION": 15,
        "ELIGIBILITY": 20,
        "VALIDATION": 35,
        "COMPLIANCE": 50,
        "SUBMISSION": 65,
        "CLEARINGHOUSE": 70,
        "ACKNOWLEDGMENT": 74,
        "PAYER_ACKNOWLEDGMENT": 74,
        "DENIAL": 80,
        "DENIAL_AI": 80,
        "PAYMENT": 85,
        "LEARNING": 92,
        "ANALYTICS": 98,
        "FINISH": 100,
        "COMPLETED": 100,
    }

    completed_progress = {
        "OCR": 15,
        "EXTRACTION": 15,
        "ELIGIBILITY": 25,
        "VALIDATION": 40,
        "COMPLIANCE": 55,
        "SUBMISSION": 65,
        "CLEARINGHOUSE": 75,
        "ACKNOWLEDGMENT": 78,
        "PAYER_ACKNOWLEDGMENT": 78,
        "DENIAL": 82,
        "DENIAL_AI": 82,
        "PAYMENT": 88,
        "LEARNING": 94,
        "ANALYTICS": 100,
        "FINISH": 100,
        "COMPLETED": 100,
    }

    if progress is not None:
        resolved_progress = progress
    elif claim.get("progress") is not None:
        resolved_progress = claim.get("progress")
    elif status_upper in {"COMPLETED", "PAID", "SUCCESS"}:
        resolved_progress = completed_progress.get(stage_upper, 100)
    else:
        resolved_progress = running_progress.get(stage_upper, 70)

    active_step = claim.get("active_step") or step_map.get(stage_upper) or stage_upper.lower()

    if pipeline_state:
        resolved_pipeline_state = pipeline_state
    elif claim.get("pipeline_state"):
        resolved_pipeline_state = claim.get("pipeline_state")
    elif status_upper in {"COMPLETED", "PAID", "SUCCESS"}:
        resolved_pipeline_state = f"{stage_upper}_COMPLETED"
    else:
        resolved_pipeline_state = f"{stage_upper}_RUNNING"

    if status_upper == "PAID":
        resolved_pipeline_state = "COMPLETED"
        resolved_progress = 100

    current_agent = (
        claim.get("current_agent")
        or {
            "ACKNOWLEDGMENT": "PAYER_ACKNOWLEDGMENT",
            "PAYER_ACKNOWLEDGMENT": "PAYER_ACKNOWLEDGMENT",
            "DENIAL": "DENIAL_AI",
            "DENIAL_AI": "DENIAL_AI",
            "PAYMENT": "PAYMENT",
            "LEARNING": "LEARNING",
            "ANALYTICS": "ANALYTICS",
            "FINISH": "ANALYTICS",
            "COMPLETED": "ANALYTICS",
        }.get(stage_upper)
        or stage_upper
    )

    is_hitl_state = (
        resolved_pipeline_state in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"}
        or status_upper in {"HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"}
        or bool(claim.get("review_required"))
        or bool(claim.get("approval_required"))
        or bool(claim.get("pipeline_paused"))
    )

    claim.update(
        {
            "stage": stage_upper,
            "status": "PAID" if status_upper == "PAID" else ("PROCESSING" if status_upper == "RUNNING" else status_upper),
            "current_stage": stage_upper,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": resolved_pipeline_state,
            "pipeline_status": status_upper,
            "progress": resolved_progress,
            "review_required": True if is_hitl_state else bool(claim.get("review_required")),
            "approval_required": True if is_hitl_state else bool(claim.get("approval_required")),
            "pipeline_paused": True if is_hitl_state else bool(claim.get("pipeline_paused")),
            "waiting_for_human": True if is_hitl_state else bool(claim.get("waiting_for_human")),
            "clearinghouse_approved": claim.get("clearinghouse_approved", True),
            "clearinghouse_accepted": claim.get("clearinghouse_accepted", True),
        }
    )

    payload = {
        "type": "agent_update",
        "event": "agent_update",
        "claim_id": claim.get("claim_id"),
        "submission_id": _claim_submission_id(claim, fallback=claim.get("claim_id")),
        "stage": stage_upper,
        "status": status_upper,
        "progress": resolved_progress,
        "current_stage": stage_upper,
        "current_agent": current_agent,
        "active_step": active_step,
        "pipeline_state": resolved_pipeline_state,
        "pipeline_status": status_upper,
        "clearinghouse_status": claim.get("clearinghouse_status"),
        "review_required": bool(claim.get("review_required")),
        "approval_required": bool(claim.get("approval_required")),
        "pipeline_paused": bool(claim.get("pipeline_paused")),
        "waiting_for_human": bool(claim.get("waiting_for_human")),
        "case": claim.get("case"),
        "case_id": claim.get("case_id"),
        "hitl_case": claim.get("hitl_case"),
        "claim": claim,
        "timestamp": _utc_now(),
    }

    await emit_once_async(manager, payload)


def _submission_waiting_for_clearinghouse(submission_state, mapped_claim, processing_mode):
    if processing_mode != "MANUAL" or mapped_claim.get("clearinghouse_approved"):
        return False

    status = _normalize_status(
        submission_state.get("status")
        or mapped_claim.get("status")
        or mapped_claim.get("pipeline_state")
        or mapped_claim.get("clearinghouse_status")
    )
    pipeline_state = _normalize_status(
        submission_state.get("pipeline_state")
        or mapped_claim.get("pipeline_state")
        or mapped_claim.get("pipeline_status")
    )
    stage = _normalize_status(
        submission_state.get("current_stage")
        or submission_state.get("stage")
        or mapped_claim.get("current_stage")
        or mapped_claim.get("stage")
    )
    active_step = _normalize_status(
        submission_state.get("active_step")
        or mapped_claim.get("active_step")
    )

    wait_states = {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "PENDING_APPROVAL"}

    return (
        status in wait_states
        or pipeline_state in wait_states
        or stage == "CLEARINGHOUSE"
        or active_step == "CLEARINGHOUSE"
        or mapped_claim.get("review_required") is True
        or _normalize_status(mapped_claim.get("clearinghouse_status")) == "PENDING_CLEARINGHOUSE"
    )


async def _pause_at_clearinghouse(
    mapped_claim,
    pipeline,
    validation,
    ch_response,
    claim_id,
    submission_id,
    job=None,
):
    pipeline.setdefault("steps", {})
    pipeline["steps"]["submitted"] = True
    pipeline["steps"]["clearinghouse_queued"] = True
    pipeline["steps"]["acknowledged"] = False
    pipeline["steps"]["denial_checked"] = False
    pipeline["steps"]["paid"] = False
    pipeline["steps"]["learning_updated"] = False
    pipeline["steps"]["analytics_done"] = False

    pipeline.update(
        {
            "queue_state": "CLEARINGHOUSE_QUEUE",
            "review_status": "WAITING_FOR_APPROVAL",
            "pipeline_paused": True,
            "review_required": True,
            "approval_required": True,
            "waiting_for_human": True,
            "progress": 70,
            "current_stage": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "current_agent": "CLEARINGHOUSE",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "submission_id": submission_id,
        }
    )

    _set_pipeline_state(
        mapped_claim,
        pipeline,
        "WAITING_FOR_APPROVAL",
        "clearinghouse",
        "WAITING_FOR_APPROVAL",
        metadata={"processing_mode": "MANUAL", "clearinghouse": ch_response},
    )

    mapped_claim.update(
        {
            "submission_id": submission_id,
            "status": "PENDING_CLEARINGHOUSE",
            "stage": "CLEARINGHOUSE",
            "queue_state": "CLEARINGHOUSE_QUEUE",
            "review_status": "WAITING_FOR_APPROVAL",
            "pipeline_paused": True,
            "review_required": True,
            "approval_required": True,
            "waiting_for_human": True,
            "progress": 70,
            "current_stage": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "current_agent": "CLEARINGHOUSE",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
        }
    )

    pipeline_log(
        "CLEARINGHOUSE",
        "Waiting for clearinghouse response",
        claim_id=claim_id,
        submission_id=submission_id,
        status="WAITING_FOR_APPROVAL",
    )

    await emit_pipeline_event(
        "CLEARINGHOUSE",
        "WAITING_FOR_APPROVAL",
        "Claim is waiting for clearinghouse approval",
        claim_id=claim_id,
        submission_id=submission_id,
        metadata={
            "clearinghouse": ch_response,
            "current_stage": "CLEARINGHOUSE",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "review_required": True,
            "approval_required": True,
            "pipeline_paused": True,
            "progress": 70,
        },
    )

    await _emit_agent_update(
        mapped_claim,
        "CLEARINGHOUSE",
        "WAITING_FOR_APPROVAL",
        progress=70,
        pipeline_state="WAITING_FOR_APPROVAL",
    )

    record = _build_pipeline_record(
        mapped_claim,
        "WAITING_FOR_APPROVAL",
        pipeline,
        validation=validation,
        clearinghouse=ch_response,
    )

    _schedule_pipeline_record_save(
        mapped_claim,
        "WAITING_FOR_APPROVAL",
        pipeline,
        validation=validation,
        clearinghouse=ch_response,
    )

    _mark_step(job, "submission", "COMPLETED")
    _mark_step(job, "clearinghouse", "WAITING_FOR_APPROVAL")

    await manager.broadcast(
        {
            "type": "clearinghouse_queued",
            "event": "clearinghouse_queued",
            "claim_id": claim_id,
            "submission_id": submission_id,
            "stage": "CLEARINGHOUSE",
            "step": "clearinghouse",
            "status": "WAITING_FOR_APPROVAL",
            "queue_state": "CLEARINGHOUSE_QUEUE",
            "current_agent": "CLEARINGHOUSE",
            "current_stage": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "pipeline_paused": True,
            "review_required": True,
            "approval_required": True,
            "waiting_for_human": True,
            "pipeline": pipeline,
            "claim": mapped_claim,
            "completed_stages": mapped_claim.get("completed_stages", []),
            "pending_stages": ["DENIAL_AI", "PAYMENT", "LEARNING", "ANALYTICS"],
            "progress": 70,
            "event_version": pipeline.get("event_version"),
            "stage_order": pipeline.get("stage_order"),
            "timestamp": _utc_now(),
        }
    )

    return {
        "claim_id": claim_id,
        "submission_id": submission_id,
        "status": "WAITING_FOR_APPROVAL",
        "stage": "CLEARINGHOUSE",
        "current_stage": "CLEARINGHOUSE",
        "current_agent": "CLEARINGHOUSE",
        "active_step": "clearinghouse",
        "pipeline_state": "WAITING_FOR_APPROVAL",
        "pipeline_status": "WAITING_FOR_APPROVAL",
        "clearinghouse_status": "PENDING_CLEARINGHOUSE",
        "review_required": True,
        "approval_required": True,
        "pipeline_paused": True,
        "record": record,
        "pipeline": pipeline,
        "claim": mapped_claim,
    }


async def run_denial_document_pipeline(claim, job=None):
    claim = claim or {}
    claim_id = claim.get("claim_id", "UNKNOWN")

    existing_denial = (
        claim.get("denial")
        if isinstance(claim.get("denial"), dict)
        else {}
    )

    claim.update(
        {
            "status": "DENIAL_AI_RUNNING",
            "pipeline_state": "DENIAL_AI_RUNNING",
            "pipeline_status": "RUNNING",
            "current_stage": "DENIAL_AI",
            "current_agent": "DENIAL_AI",
            "active_step": "denial_ai",
            "requires_human_review": False,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "progress": 70,
        }
    )

    await manager.broadcast(
        {
            "type": "agent_update",
            "event": "agent_update",
            "claim_id": claim_id,
            "stage": "DENIAL_AI",
            "status": "RUNNING",
            "progress": 70,
            "current_stage": "DENIAL_AI",
            "current_agent": "DENIAL_AI",
            "active_step": "denial_ai",
            "pipeline_state": "DENIAL_AI_RUNNING",
            "pipeline_status": "RUNNING",
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "claim": claim,
        }
    )

    denial_result = await LLMDenialAgent().run(claim, existing_denial)

    if isinstance(denial_result, dict):
        claim["denial_ai"] = denial_result.get("denial_ai") or denial_result
        claim["appeal"] = (
            denial_result.get("appeal")
            or denial_result.get("appeal_draft")
        )
        claim["analysis"] = denial_result.get("analysis") or denial_result
    else:
        claim["denial_ai"] = denial_result
        claim["analysis"] = denial_result

    claim.update(
        {
            "status": "DENIAL_ANALYZED",
            "pipeline_state": "DENIAL_ANALYZED",
            "pipeline_status": "DENIAL_ANALYZED",
            "current_stage": "DENIAL_AI",
            "current_agent": "DENIAL_AI",
            "active_step": "denial_ai_completed",
            "progress": 100,
            "requires_human_review": False,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
        }
    )

    save_claim(
        claim_id,
        "DENIAL_ANALYZED",
        "DENIAL_AI",
        claim,
        total_charge=claim.get("total_charge", 0),
    )

    await manager.broadcast(
        {
            "type": "agent_update",
            "event": "agent_update",
            "claim_id": claim_id,
            "stage": "DENIAL_AI",
            "status": "COMPLETED",
            "progress": 100,
            "current_stage": "DENIAL_AI",
            "current_agent": "DENIAL_AI",
            "active_step": "denial_ai_completed",
            "pipeline_state": "DENIAL_ANALYZED",
            "pipeline_status": "DENIAL_ANALYZED",
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "claim": claim,
        }
    )

    return {
        "claim_id": claim_id,
        "status": "DENIAL_ANALYZED",
        "stage": "DENIAL_AI",
        "current_stage": "DENIAL_AI",
        "current_agent": "DENIAL_AI",
        "active_step": "denial_ai_completed",
        "pipeline_state": "DENIAL_ANALYZED",
        "pipeline_status": "DENIAL_ANALYZED",
        "claim": claim,
        "denial_ai": claim.get("denial_ai"),
        "appeal": claim.get("appeal"),
        "analysis": claim.get("analysis"),
    }

async def run_claim_pipeline(mapped_claim, job=None, skip_validation=False):
    mapped_claim = mapped_claim or {}

    document_type = str(
        mapped_claim.get("document_type")
        or mapped_claim.get("form_type")
        or mapped_claim.get("claim_type")
        or ""
    ).upper()

    status = str(
        mapped_claim.get("status")
        or mapped_claim.get("confidence_status")
        or mapped_claim.get("pipeline_status")
        or ""
    ).upper()

    is_denial_ai_claim = (
        document_type == "EOB_ERA"
        or mapped_claim.get("denial_ai_required") is True
        or mapped_claim.get("denial_required") is True
        or status == "DENIAL_AI_REQUIRED"
    )

    if is_denial_ai_claim:
        print(
            f"🧠 [Pipeline] EOB/ERA detected. Routing directly to Denial AI: "
            f"claim_id={mapped_claim.get('claim_id')}, "
            f"document_type={document_type}, status={status}",
            flush=True,
        )
        return await run_denial_document_pipeline(mapped_claim, job=job)

    claim_id = mapped_claim.get("claim_id")
    
    submission_id = _claim_submission_id(mapped_claim, fallback=claim_id)
    if submission_id.startswith("SUB-"):
        _sync_submission_id(mapped_claim)
    else:
        mapped_claim["submission_id"] = submission_id

    extraction = mapped_claim.get("extraction") or {}
    detected_form_type = detect_form_type_from_payload(mapped_claim)
    mapped_claim["form_type"] = mapped_claim.get("form_type") or detected_form_type
    if extraction:
        await emit_pipeline_event(
            "EXTRACTION",
            "SUCCESS",
            "Universal extraction confidence scored",
            claim_id=claim_id,
            submission_id=submission_id,
            metadata=extraction,
        )

    extraction_confidence = (
        extraction.get("extraction_confidence")
        or extraction.get("confidence")
        or extraction.get("confidence_score")
        or mapped_claim.get("confidence")
        or 100
    )
    try:
        extraction_confidence = float(extraction_confidence)
    except (TypeError, ValueError):
        extraction_confidence = 100

    extraction_confidence_percent = extraction_confidence * 100 if 0 < extraction_confidence <= 1 else extraction_confidence
    extraction_confidence_decimal = max(0, min(100, extraction_confidence_percent)) / 100
    confidence_status = claim_confidence_status(extraction_confidence_decimal)
    if confidence_status:
        mapped_claim["confidence_status"] = confidence_status
        if confidence_status in {"AUTO_APPROVED", "VALIDATION_REQUIRED"}:
            mapped_claim["status"] = confidence_status

    hitl_reasons = hitl_reasons_for_claim(mapped_claim)
    mapped_claim["extraction_summary"] = {
        "confidence_score": round(extraction_confidence_decimal, 4),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "confidence_status": confidence_status,
        "extraction_status": "SUCCESS" if extraction_confidence_decimal >= CONFIDENCE_THRESHOLD and not hitl_reasons else "REVIEW_REQUIRED",
        "hitl_required": bool(hitl_reasons),
        "hitl_reason": hitl_reasons,
        "form_type": detected_form_type,
        "detected_form_type": detected_form_type,
        "extracted_field_count": len(extraction.get("fields") or extraction.get("extracted_fields") or mapped_claim.keys()),
        "extracted_services_count": len(mapped_claim.get("services") or []),
        "processing_duration": extraction.get("processing_duration") or extraction.get("processing_time"),
    }

    if confidence_status == "HUMAN_REVIEW_REQUIRED":
        pipeline = _pipeline_steps(case_orchestrated=True)
        issues = [
            f"Low extraction confidence: {extraction_confidence_percent}%",
            f"Service extraction: {extraction.get('service_confidence', 0)}%",
            *hitl_reasons,
        ]
        issues = list(dict.fromkeys(issues))
        case = build_case_record(mapped_claim, issues=issues)
        update_case(mapped_claim.get("claim_id"), status="OPEN", error="; ".join(issues))
        await emit_pipeline_event(
            "EXTRACTION",
            "HUMAN_REVIEW_REQUIRED",
            "Low confidence extraction routed to HITL",
            claim_id=claim_id,
            submission_id=submission_id,
            case_id=case.get("case_id"),
            metadata=extraction,
        )
        record = _build_pipeline_record(
            mapped_claim,
            "HUMAN_REVIEW_REQUIRED",
            pipeline,
            validation={
                "valid": False,
                "validation_score": extraction.get("validation_score"),
                "extraction_confidence": extraction.get("extraction_confidence"),
                "errors": issues,
            },
            case=case,
        )
        _schedule_pipeline_record_save(
            mapped_claim,
            "HUMAN_REVIEW_REQUIRED",
            pipeline,
            validation={
                "valid": False,
                "validation_score": extraction.get("validation_score"),
                "extraction_confidence": extraction.get("extraction_confidence"),
                "errors": issues,
            },
            case=case,
        )
        return {
            "claim_id": mapped_claim.get("claim_id"),
            "status": "HUMAN_REVIEW_REQUIRED",
            "case": case,
            "record": record,
        }

    pipeline = _pipeline_steps()
    _set_pipeline_state(mapped_claim, pipeline, "OCR_COMPLETED", "extract", "COMPLETED", completed=True, metadata=extraction)
    validation = {"valid": True, "errors": [], "human_accepted": skip_validation}

    pipeline_log("ELIGIBILITY", "Eligibility started", claim_id=claim_id, submission_id=submission_id, status="START")
    await emit_pipeline_event("ELIGIBILITY", "START", "Eligibility started", claim_id=claim_id, submission_id=submission_id)
    _mark_step(job, "eligibility", "RUNNING")
    eligibility_state = await EligibilityAgent().run(mapped_claim)
    mapped_claim = eligibility_state.get("claim", mapped_claim)
    pipeline["steps"].update(eligibility_state.get("pipeline", {}).get("steps", {}))
    _mark_step(job, "eligibility", "COMPLETED")
    pipeline_log("ELIGIBILITY", "Eligibility completed", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await emit_pipeline_event("ELIGIBILITY", "SUCCESS", "Eligibility completed", claim_id=claim_id, submission_id=submission_id)

    if not skip_validation:
        pipeline_log("VALIDATION", "Validation started", claim_id=claim_id, submission_id=submission_id, status="START")
        await emit_pipeline_event("VALIDATION", "START", "Validation started", claim_id=claim_id, submission_id=submission_id)
        _mark_step(job, "validation", "RUNNING")
        validation_state = await ValidationAgent().run({"claim": mapped_claim})
        _save_trace_id(job, validation_state.get("trace_id"))
        mapped_claim = validation_state.get("claim", mapped_claim)
        validation = validation_state.get("validation", validation)
        validation_state["validation_result"] = validation_state.get("validation_result") or validation
        mapped_claim["validation_result"] = validation
        mapped_claim = _apply_quality_metrics(mapped_claim, validation)

        if not validation.get("valid", True):
            _mark_step(job, "ai_suggestions", "RUNNING")
            repair_state = await ClaimRepairEngine().repair_and_retry(
                {
                    "claim": mapped_claim,
                    "validation": validation,
                    "validation_result": validation_state.get("validation_result") or validation,
                    "retry_mode": True,
                    "pipeline": pipeline,
                },
                max_retries=1,
            )
            mapped_claim = repair_state.get("claim", mapped_claim)
            validation = repair_state.get("validation", validation)
            mapped_claim["validation_result"] = validation
            mapped_claim["ai_suggestions"] = repair_state.get("ai_suggestions", [])
            mapped_claim["correction_history"] = repair_state.get("correction_history", [])
            pipeline["steps"]["ai_suggestions"] = True
            pipeline["steps"]["auto_corrected"] = bool(mapped_claim.get("correction_history"))
            pipeline["steps"]["validation_retry"] = True
            _mark_step(job, "ai_suggestions", "COMPLETED")

        if not validation.get("valid", True):
            review_required = bool(
                mapped_claim.get("requires_hitl")
                or mapped_claim.get("pipeline_state") == "WAITING_FOR_REVIEW"
            )
            review_state = "WAITING_FOR_REVIEW" if review_required else "HITL_REQUIRED"
            _mark_step(job, "validation", "FAILED")
            _set_pipeline_state(
                mapped_claim,
                pipeline,
                review_state,
                "waiting_for_review" if review_required else "validation",
                review_state,
                metadata={"validation": validation},
            )
            if review_required:
                mapped_claim["requires_hitl"] = True
                mapped_claim["status"] = "WAITING_FOR_REVIEW"
                mapped_claim["review_state"] = "PENDING_REVIEW"
                mapped_claim["queue_state"] = "HUMAN_REVIEW"
                mapped_claim["review_required"] = True
                mapped_claim["waiting_for_human"] = True
                mapped_claim["current_stage"] = "WAITING_FOR_REVIEW"
                mapped_claim["active_step"] = "waiting_for_review"
                mapped_claim["current_agent"] = "SUBMISSION_REVIEW"
                pipeline["pipeline_state"] = "WAITING_FOR_REVIEW"
                pipeline["pipeline_status"] = "WAITING_FOR_REVIEW"
                pipeline["current_stage"] = "WAITING_FOR_REVIEW"
                pipeline["active_step"] = "waiting_for_review"
                pipeline["current_agent"] = "SUBMISSION_REVIEW"
                pipeline["review_required"] = True
                pipeline["waiting_for_human"] = True
            pipeline_log("VALIDATION", "Validation failed; review required", claim_id=claim_id, submission_id=submission_id, status="WARNING")
            await _emit_agent_update(
                mapped_claim,
                "WAITING_FOR_REVIEW" if review_required else "VALIDATION",
                review_state,
                progress=mapped_claim.get("progress"),
                pipeline_state=review_state,
            )
            await emit_pipeline_event("VALIDATION", "ERROR", "Validation failed; review required", claim_id=claim_id, submission_id=submission_id)

            issues = validation.get("errors") or ["Validation failed"]
            case = build_case_record(mapped_claim, issues=issues)
            pipeline["steps"]["case_orchestrated"] = True
            pipeline_log("CASE_ORCHESTRATOR", "REVIEW REQUIRED", claim_id=claim_id, submission_id=submission_id, case_id=case.get("case_id"), status="WARNING")
            pipeline_log("CASE_ORCHESTRATOR", "Case created", claim_id=claim_id, submission_id=submission_id, case_id=case.get("case_id"), status="INFO")
            pipeline_log("CASE_ORCHESTRATOR", "Assigned to QA_TEAM", claim_id=claim_id, submission_id=submission_id, case_id=case.get("case_id"), status="INFO")
            await emit_pipeline_event(
                "CASE_ORCHESTRATOR",
                "WARNING",
                "REVIEW REQUIRED",
                claim_id=claim_id,
                submission_id=submission_id,
                case_id=case.get("case_id"),
                metadata={"assigned_to": "QA_TEAM", "issues": issues},
            )

            pipeline_log("DB_AGENT", "Saving HITL case to PostgreSQL", claim_id=claim_id, submission_id=submission_id, case_id=case.get("case_id"), status="DB")
            update_case(mapped_claim.get("claim_id"), status="OPEN", error="; ".join(str(issue) for issue in issues))
            pipeline_log("DB_AGENT", "HITL case saved successfully", claim_id=claim_id, submission_id=submission_id, case_id=case.get("case_id"), status="SUCCESS")
            record_status = "WAITING_FOR_REVIEW" if review_required else "needs_review"
            record = _build_pipeline_record(mapped_claim, record_status, pipeline, validation=validation, case=case)
            _schedule_pipeline_record_save(mapped_claim, record_status, pipeline, validation=validation, case=case)

            return {
                "claim_id": mapped_claim.get("claim_id"),
                "status": "WAITING_FOR_REVIEW" if review_required else "HITL_REQUIRED",
                "case": case,
                "record": record,
            }

        pipeline["steps"]["rules_validated"] = True
        mapped_claim = _apply_quality_metrics(mapped_claim, validation)
        _set_pipeline_state(mapped_claim, pipeline, "VALIDATION_COMPLETED", "validation", "COMPLETED", completed=True, metadata={"validation": validation})
        await _emit_agent_update(mapped_claim, "VALIDATION", "COMPLETED", progress=40, pipeline_state="VALIDATION_COMPLETED")
        await _broadcast_claim_available(mapped_claim, pipeline, "VALIDATION_COMPLETED")
        await manager.broadcast({
            "type": "validation_completed",
            "event": "validation_completed",
            "claim_id": claim_id,
            "status": "COMPLETED",
            "current_stage": mapped_claim.get("current_stage"),
            "current_agent": mapped_claim.get("current_agent"),
            "active_step": mapped_claim.get("active_step"),
            "validation_score": mapped_claim.get("validation_score"),
            "ocr_confidence": mapped_claim.get("ocr_confidence"),
            "ai_confidence": mapped_claim.get("ai_confidence"),
            "pipeline_state": mapped_claim.get("pipeline_state"),
            "progress": mapped_claim.get("progress") or pipeline.get("progress"),
            "timestamp": _utc_now(),
        })
        _mark_step(job, "validation", "COMPLETED")
        pipeline_log("VALIDATION", "Validation completed successfully", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
        await emit_pipeline_event("VALIDATION", "SUCCESS", "Validation completed successfully", claim_id=claim_id, submission_id=submission_id)
    else:
        pipeline["steps"]["case_orchestrated"] = True
        pipeline["steps"]["rules_validated"] = True
        _set_pipeline_state(mapped_claim, pipeline, "VALIDATION_COMPLETED", "validation", "COMPLETED", completed=True, metadata={"human_accepted": True})
        _mark_step(job, "validation", "HUMAN_ACCEPTED")

    pipeline_log("COMPLIANCE", "Compliance started", claim_id=claim_id, submission_id=submission_id, status="START")
    await emit_pipeline_event("COMPLIANCE", "START", "Compliance started", claim_id=claim_id, submission_id=submission_id)
    _mark_step(job, "compliance", "RUNNING")
    compliance_state = await ComplianceAgent().run(mapped_claim)
    mapped_claim = compliance_state.get("claim", mapped_claim)
    pipeline["steps"]["compliance_checked"] = True
    compliance_result = compliance_state.get("compliance") or mapped_claim.get("compliance") or {}
    compliance_result_status = _normalize_status(
        compliance_state.get("status")
        or compliance_state.get("compliance_status")
        or mapped_claim.get("compliance_status")
    )
    hard_reject = bool(
        compliance_result.get("hard_reject")
        or compliance_state.get("hard_reject")
        or mapped_claim.get("hard_reject")
        or compliance_result_status == "HARD_REJECT"
    )
    compliance_failed = bool(
        compliance_result.get("hitl_required")
        or compliance_state.get("hitl_required")
        or mapped_claim.get("hitl_required")
    )
    _set_pipeline_state(
        mapped_claim,
        pipeline,
        "HARD_REJECT" if hard_reject else "HITL_REQUIRED" if compliance_failed else "COMPLIANCE_COMPLETED",
        "compliance",
        "HARD_REJECT" if hard_reject else "HITL_REQUIRED" if compliance_failed else "COMPLETED",
        completed=not compliance_failed and not hard_reject,
        metadata={"compliance": compliance_result},
    )
    await _emit_agent_update(
        mapped_claim,
        "COMPLIANCE",
        "FAILED" if (compliance_failed or hard_reject) else "COMPLETED",
        progress=60,
        pipeline_state=mapped_claim.get("pipeline_state"),
    )

    if not hard_reject and not compliance_failed:
        _schedule_pipeline_record_save(mapped_claim, mapped_claim.get("pipeline_state"), pipeline, validation=validation)

    await _broadcast_claim_available(mapped_claim, pipeline, mapped_claim.get("pipeline_state"))
    await manager.broadcast({
        "type": "compliance_completed",
        "event": "compliance_completed",
        "claim_id": claim_id,
        "status": mapped_claim.get("pipeline_status"),
        "current_stage": mapped_claim.get("current_stage"),
        "current_agent": mapped_claim.get("current_agent"),
        "active_step": mapped_claim.get("active_step"),
        "pipeline_state": mapped_claim.get("pipeline_state"),
        "progress": mapped_claim.get("progress") or pipeline.get("progress"),
        "timestamp": _utc_now(),
    })
    _mark_step(job, "compliance", "FAILED" if (compliance_failed or hard_reject) else "COMPLETED")
    pipeline_log(
        "COMPLIANCE",
        "Compliance hard rejected; pipeline stopped" if hard_reject else "Compliance failed; pipeline paused for HITL" if compliance_failed else "Compliance completed",
        claim_id=claim_id,
        submission_id=submission_id,
        status="STOP" if hard_reject else "WARNING" if compliance_failed else "SUCCESS",
    )
    await emit_pipeline_event(
        "COMPLIANCE",
        "HARD_REJECT" if hard_reject else "HITL_REQUIRED" if compliance_failed else "SUCCESS",
        "Compliance hard rejected; pipeline stopped" if hard_reject else "Compliance failed; pipeline paused for HITL" if compliance_failed else "Compliance completed",
        claim_id=claim_id,
        submission_id=submission_id,
        metadata={
            "status": compliance_state.get("compliance_status"),
            "terminal": compliance_failed or hard_reject,
            "compliance": compliance_result,
            "failure_reason": compliance_result.get("reason"),
            "failed_rule": compliance_result.get("rule"),
            "severity": compliance_result.get("severity"),
            "pipeline_state": mapped_claim.get("pipeline_state"),
            "pipeline_status": mapped_claim.get("pipeline_status"),
            "current_agent": mapped_claim.get("current_agent"),
            "current_stage": mapped_claim.get("current_stage"),
            "active_step": mapped_claim.get("active_step"),
            "completed_stages": mapped_claim.get("completed_stages", []),
            "stage_history": mapped_claim.get("stage_history", []),
        },
    )

    if hard_reject:
        mapped_claim["failure_reason"] = compliance_result.get("reason")
        mapped_claim["failed_rule"] = compliance_result.get("rule")
        mapped_claim["pipeline_state"] = "HARD_REJECT"
        mapped_claim["pipeline_status"] = "HARD_REJECT"
        mapped_claim["status"] = "HARD_REJECT"
        mapped_claim["current_stage"] = "COMPLIANCE"
        mapped_claim["current_agent"] = "Compliance"
        mapped_claim["active_step"] = "compliance"
        mapped_claim["hard_reject"] = True
        mapped_claim["review_required"] = False
        mapped_claim["waiting_for_human"] = False
        mapped_claim["pipeline_paused"] = False

        pipeline.setdefault("steps", {})
        pipeline["steps"]["hard_reject"] = True
        pipeline["pipeline_state"] = "HARD_REJECT"
        pipeline["pipeline_status"] = "HARD_REJECT"
        pipeline["current_stage"] = "COMPLIANCE"
        pipeline["current_agent"] = "Compliance"
        pipeline["active_step"] = "compliance"
        pipeline["terminal"] = True

        return await _return_terminal_state(
            mapped_claim,
            "HARD_REJECT",
            pipeline,
            validation=validation,
            clearinghouse=None,
            message="Compliance hard reject stopped pipeline before submission",
        )

    if compliance_failed:
        issues = (
            compliance_result.get("issues")
            or compliance_state.get("audit", {}).get("issues")
            or [compliance_result.get("reason") or "Compliance failed"]
        )

        case = build_case_record(mapped_claim, issues=issues)
        update_case(mapped_claim.get("claim_id"), status="OPEN", error="; ".join(str(issue) for issue in issues))


        mapped_claim["compliance_warning"] = True
        mapped_claim["failure_reason"] = compliance_result.get("reason")
        mapped_claim["failed_rule"] = compliance_result.get("rule")
        mapped_claim["status"] = "HITL_REQUIRED"
        mapped_claim["pipeline_state"] = "HITL_REQUIRED"
        mapped_claim["pipeline_status"] = "HITL_REQUIRED"
        mapped_claim["current_stage"] = "CASE_ORCHESTRATOR"
        mapped_claim["current_agent"] = "CASE_ORCHESTRATOR"
        mapped_claim["active_step"] = "case_orchestrator"
        mapped_claim["queue_state"] = "HUMAN_REVIEW"
        mapped_claim["review_status"] = "PENDING_REVIEW"
        mapped_claim["review_required"] = True
        mapped_claim["approval_required"] = True
        mapped_claim["pipeline_paused"] = True
        mapped_claim["waiting_for_human"] = True
        mapped_claim["progress"] = 60

        pipeline["steps"]["compliance_warning"] = True
        pipeline["steps"]["case_orchestrated"] = True
        pipeline["case"] = case
        pipeline["case_id"] = case.get("case_id")
        pipeline["pipeline_state"] = "HITL_REQUIRED"
        pipeline["pipeline_status"] = "HITL_REQUIRED"
        pipeline["current_stage"] = "CASE_ORCHESTRATOR"
        pipeline["current_agent"] = "CASE_ORCHESTRATOR"
        pipeline["active_step"] = "case_orchestrator"
        pipeline["review_required"] = True
        pipeline["approval_required"] = True
        pipeline["pipeline_paused"] = True
        pipeline["waiting_for_human"] = True
        pipeline["progress"] = 60


        await emit_pipeline_event(
            "CASE_ORCHESTRATOR",
            "HITL_REQUIRED",
            "Compliance warning routed to HITL queue",
            claim_id=claim_id,
            submission_id=submission_id,
            case_id=case.get("case_id"),
            metadata={"assigned_to": "QA_TEAM", "issues": issues, "terminal": True},
        )

        pipeline_log(
            "COMPLIANCE",
            "Compliance HITL case created; pipeline paused before submission",
            claim_id=claim_id,
            submission_id=submission_id,
            status="WARNING",
        )

        mapped_claim["compliance_warning"] = True
        mapped_claim["failure_reason"] = compliance_result.get("reason")
        mapped_claim["failed_rule"] = compliance_result.get("rule")
        mapped_claim["pipeline_status"] = "PAUSED"
        mapped_claim["current_stage"] = "COMPLIANCE"
        pipeline["steps"]["compliance_warning"] = True
        mapped_claim["status"] = "HITL_REQUIRED"

        await manager.broadcast(
            {
                "type": "hitl_case_created",
                "event": "hitl_case_created",
                "claim_id": claim_id,
                "submission_id": submission_id,
                "case_id": case.get("case_id"),
                "stage": "CASE_ORCHESTRATOR",
                "status": "HITL_REQUIRED",
                "progress": 60,
                "current_stage": "CASE_ORCHESTRATOR",
                "current_agent": "CASE_ORCHESTRATOR",
                "active_step": "case_orchestrator",
                "pipeline_state": "HITL_REQUIRED",
                "pipeline_status": "HITL_REQUIRED",
                "review_required": True,
                "approval_required": True,
                "pipeline_paused": True,
                "waiting_for_human": True,
                "case": case,
                "hitl_case": case,
                "claim": mapped_claim,
                "pipeline": pipeline,
                "timestamp": _utc_now(),
            }
        )


        
        return await _return_terminal_state(
            mapped_claim,
            "HITL_REQUIRED",
            pipeline,
            validation=validation,
            case=case,
            message="Compliance failed; HITL approval required before submission",
        )

    processing_mode = str(
        mapped_claim.get("clearinghouse_processing_mode")
        or mapped_claim.get("processing_mode")
        or "MANUAL"
    ).upper()

    _mark_step(job, "submission", "RUNNING")
    _mark_step(job, "edi_generation", "RUNNING")
    pipeline["steps"]["edi_generation"] = True
    _mark_step(job, "edi_generation", "COMPLETED")

    pipeline_log("SUBMISSION", "Submitting claim to clearinghouse", claim_id=claim_id, submission_id=submission_id, status="PROCESS")
    _set_pipeline_state(mapped_claim, pipeline, "CLEARINGHOUSE_PENDING", "submission", "RUNNING", metadata={"processing_mode": processing_mode})
    await emit_pipeline_event("SUBMISSION", "PROCESS", "Submitting claim to clearinghouse", claim_id=claim_id, submission_id=submission_id)

    submission_state = await SubmissionAgent().run(mapped_claim)
    mapped_claim = submission_state.get("claim", mapped_claim)
    
    submission_status = _normalize_status(
    submission_state.get("status")
    or mapped_claim.get("status")
    or mapped_claim.get("pipeline_state")
    or mapped_claim.get("pipeline_status")
)

    submission_stage = _normalize_status(
        submission_state.get("stage")
        or submission_state.get("current_stage")
        or mapped_claim.get("stage")
        or mapped_claim.get("current_stage")
    )

    submission_pipeline_state = _normalize_status(
        submission_state.get("pipeline_state")
        or submission_state.get("pipeline_status")
        or mapped_claim.get("pipeline_state")
        or mapped_claim.get("pipeline_status")
    )

    submission_clearinghouse_status = _normalize_status(
        submission_state.get("clearinghouse_status")
        or mapped_claim.get("clearinghouse_status")
    )

    if (
        submission_status in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "PENDING_APPROVAL"}
        or submission_pipeline_state in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "PENDING_APPROVAL"}
        or submission_clearinghouse_status == "PENDING_CLEARINGHOUSE"
        or submission_stage == "CLEARINGHOUSE"
        or mapped_claim.get("review_required") is True
        or mapped_claim.get("approval_required") is True
    ):
        submission_id = (
            submission_state.get("submission_id")
            or mapped_claim.get("submission_id")
            or _claim_submission_id(mapped_claim, fallback=claim_id)
        )

        mapped_claim.update(
            {
                "status": "PENDING_CLEARINGHOUSE",
                "stage": "CLEARINGHOUSE",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "pipeline_status": "WAITING_FOR_APPROVAL",
                "pipeline_result": "WAITING_FOR_APPROVAL",
                "clearinghouse_status": "PENDING_CLEARINGHOUSE",
                "review_required": True,
                "approval_required": True,
                "pipeline_paused": True,
                "progress": 70,
                "submission_id": submission_id,
            }
        )

        pipeline["steps"]["submitted"] = True
        pipeline["steps"]["clearinghouse_queued"] = True
        pipeline["steps"]["clearinghouse_accepted"] = False
        pipeline["steps"]["acknowledged"] = False
        pipeline["steps"]["denial_checked"] = False
        pipeline["steps"]["paid"] = False
        pipeline["steps"]["learning_updated"] = False
        pipeline["steps"]["analytics_done"] = False

        pipeline.update(
            {
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "pipeline_status": "WAITING_FOR_APPROVAL",
                "pipeline_result": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "clearinghouse_status": "PENDING_CLEARINGHOUSE",
                "review_required": True,
                "approval_required": True,
                "pipeline_paused": True,
                "progress": 70,
            }
        )

        pipeline_log(
            "CLEARINGHOUSE",
            "Pipeline paused at clearinghouse approval",
            claim_id=claim_id,
            submission_id=submission_id,
            status="WAITING_FOR_APPROVAL",
        )

        await _emit_agent_update(
            mapped_claim,
            "CLEARINGHOUSE",
            "WAITING_FOR_APPROVAL",
            progress=70,
            pipeline_state="WAITING_FOR_APPROVAL",
        )

        return {
            "claim_id": claim_id,
            "submission_id": submission_id,
            "status": "WAITING_FOR_APPROVAL",
            "stage": "CLEARINGHOUSE",
            "current_stage": "CLEARINGHOUSE",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "pipeline_state": "WAITING_FOR_APPROVAL",
            "pipeline_status": "WAITING_FOR_APPROVAL",
            "pipeline_result": "WAITING_FOR_APPROVAL",
            "clearinghouse_status": "PENDING_CLEARINGHOUSE",
            "review_required": True,
            "approval_required": True,
            "pipeline_paused": True,
            "progress": 70,
            "claim": mapped_claim,
            "pipeline": pipeline,
        }

    submission_id = (
        _sync_submission_id(mapped_claim)
        or submission_state.get("submission_id")
        or _claim_submission_id(mapped_claim, fallback=claim_id)
    )

    ch_response = (
        mapped_claim.get("submission")
        or submission_state.get("clearinghouse")
        or submission_state.get("clearinghouse_response")
        or {}
    )
    if isinstance(ch_response, dict) and submission_id.startswith("SUB-"):
        ch_response["submission_id"] = submission_id

    # CRITICAL FIX:
    # If SubmissionAgent already moved the claim to CLEARINGHOUSE / WAITING_FOR_APPROVAL,
    # return immediately. Do not emit SUBMISSION / COMPLETED afterward, because that stale
    # event overwrites the live frontend state.
    if _submission_waiting_for_clearinghouse(submission_state, mapped_claim, processing_mode):
        return await _pause_at_clearinghouse(
            mapped_claim,
            pipeline,
            validation,
            ch_response,
            claim_id,
            submission_id,
            job=job,
        )

    pipeline_log("SUBMISSION", "Submission successful", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await emit_pipeline_event(
        "SUBMISSION",
        "SUCCESS",
        "Claim submitted",
        claim_id=claim_id,
        submission_id=submission_id,
        metadata={"clearinghouse": ch_response},
    )
    pipeline["steps"]["submitted"] = True
    _set_pipeline_state(
        mapped_claim,
        pipeline,
        "CLEARINGHOUSE_SUBMITTED",
        "submission",
        "COMPLETED",
        completed=True,
        metadata={"clearinghouse": ch_response},
    )
    # await _emit_agent_update(mapped_claim, "SUBMISSION", "COMPLETED", progress=65, pipeline_state="CLEARINGHOUSE_SUBMITTED")
    # Do not emit SUBMISSION/COMPLETED here for manual clearinghouse mode.
# It overrides the later CLEARINGHOUSE/WAITING_FOR_APPROVAL state in the frontend.
 
    _schedule_pipeline_record_save(mapped_claim, "PENDING_CLEARINGHOUSE", pipeline, validation=validation, clearinghouse=ch_response)
    _mark_step(job, "submission", "COMPLETED")
    
    if processing_mode == "MANUAL" and not mapped_claim.get("clearinghouse_approved"):
        await _emit_agent_update(
            mapped_claim,
            "SUBMISSION",
            "COMPLETED",
            progress=65,
            pipeline_state="CLEARINGHOUSE_SUBMITTED",
        )
    if isinstance(ch_response, dict) and ch_response.get("status") == "REJECTED":
        issue = ch_response.get("error") or "Clearinghouse rejected claim"
        case = build_case_record(mapped_claim, issues=[issue])
        update_case(mapped_claim.get("claim_id"), status="OPEN", error=issue)
        await emit_pipeline_event(
            "SUBMISSION",
            "REJECTED",
            "Clearinghouse rejected claim; pipeline stopped",
            claim_id=claim_id,
            submission_id=submission_id,
            metadata={"clearinghouse": ch_response, "terminal": True},
        )
        return await _return_terminal_state(
            mapped_claim,
            "REJECTED",
            pipeline,
            validation=validation,
            case=case,
            clearinghouse=ch_response,
            message="Rejected submission stopped pipeline before acknowledgment",
        )

    ack_999 = generate_999_ack()
    ack_277 = generate_277ca(submission_id, True)
    mapped_claim["ack"] = {"ack_999": ack_999, "ack_277": ack_277}
    pipeline["steps"]["acknowledged"] = True
    _set_pipeline_state(mapped_claim, pipeline, "ACK_RECEIVED", "clearinghouse", "COMPLETED", completed=True, metadata={"ack": mapped_claim["ack"]})
    _schedule_pipeline_record_save(mapped_claim, "PENDING_CLEARINGHOUSE", pipeline, validation=validation, clearinghouse=ch_response)
    _mark_step(job, "acknowledgment", "COMPLETED")
    pipeline_log("ACKNOWLEDGMENT", "Acknowledgment completed", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await emit_pipeline_event("ACKNOWLEDGMENT", "SUCCESS", "Acknowledgment completed", claim_id=claim_id, submission_id=submission_id)

    _set_pipeline_state(mapped_claim, pipeline, "PAYER_PENDING", "payer", "RUNNING", metadata={"ack": mapped_claim.get("ack")})
    mapped_claim["payer_response"] = {
        "status": str(mapped_claim.get("payer_response", {}).get("status") or "ADJUDICATED").upper(),
        "adjudication_status": str(mapped_claim.get("payer_response", {}).get("adjudication_status") or "ACCEPTED").upper(),
        "received_at": _utc_now(),
    }
    await _emit_stage_state("PAYER", "PENDING", "Payer response pending after clearinghouse acknowledgment", mapped_claim, pipeline)
    _schedule_pipeline_record_save(mapped_claim, "PENDING_CLEARINGHOUSE", pipeline, validation=validation, clearinghouse=ch_response)

    _mark_step(job, "denial_check", "RUNNING")
    _set_pipeline_state(mapped_claim, pipeline, "DENIAL_ANALYSIS", "denial_ai", "RUNNING", metadata={"payer_response": mapped_claim.get("payer_response")})
    denial = predict_denial(mapped_claim)
    pipeline["steps"]["denial_checked"] = True

    high_denial_risk = denial.get("denial_risk", 0) > 0.7 or denial.get("risk") == "HIGH"
    payer_rejected = str(
        mapped_claim.get("payer_response", {}).get("status")
        or mapped_claim.get("payer_response", {}).get("adjudication_status")
        or ""
    ).upper() in {"REJECTED", "DENIED"}

    if high_denial_risk and payer_rejected:
        _mark_step(job, "denial_check", "DENIED")
        denial_ai_state = await LLMDenialAgent().run(mapped_claim, denial)
        mapped_claim = denial_ai_state.get("claim", mapped_claim)
        denial = {
            **denial,
            "denial_ai": denial_ai_state.get("denial_ai", {}),
            "appeal": denial_ai_state.get("appeal", {}),
        }
        pipeline["steps"]["denial_ai_analyzed"] = True
        pipeline["steps"]["appeal_generated"] = True
        await manager.broadcast({
            "type": "agent_update",
            "event": "agent_update",
            "claim_id": claim_id,
            "stage": "DENIAL_AI",
            "status": "COMPLETED",
            "progress": mapped_claim.get("progress"),
            "current_stage": "DENIAL_AI",
            "current_agent": "DENIAL_AI",
            "active_step": "denial_ai",
            "pipeline_state": mapped_claim.get("pipeline_state"),
            "claim": mapped_claim,
            "timestamp": datetime.utcnow().isoformat(),
        })
        case = build_case_record(mapped_claim, denial=denial, issues=["Payer rejected claim with high denial risk"])
        update_case(mapped_claim.get("claim_id"), status="OPEN", error="High denial risk")
        record = _build_pipeline_record(mapped_claim, "needs_review", pipeline, validation=validation, case=case, clearinghouse=ch_response, denial=denial)
        _schedule_pipeline_record_save(mapped_claim, "needs_review", pipeline, validation=validation, case=case, clearinghouse=ch_response, denial=denial)
        return {
            "claim_id": mapped_claim.get("claim_id"),
            "status": "HITL_REQUIRED",
            "case": case,
            "record": record,
        }

    _mark_step(job, "denial_check", "CLEARED")
    _set_pipeline_state(mapped_claim, pipeline, "DENIAL_ANALYSIS", "denial_ai", "COMPLETED", completed=True, metadata=denial)
    await _emit_agent_update(mapped_claim, "DENIAL_AI", "COMPLETED", progress=80, pipeline_state="DENIAL_ANALYSIS")
    _schedule_pipeline_record_save(mapped_claim, "DENIAL_ANALYSIS", pipeline, validation=validation, clearinghouse=ch_response, denial=denial)
    pipeline_log("DENIAL", "Denial check cleared", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await emit_pipeline_event("DENIAL", "SUCCESS", "Denial check cleared", claim_id=claim_id, submission_id=submission_id, metadata=denial)

    _set_pipeline_state(mapped_claim, pipeline, "APPROVED", "payment", "RUNNING", metadata={"current_task": "Posting payment and generating ERA"})
    pipeline_log("PAYMENT", "Payment running", claim_id=claim_id, submission_id=submission_id, status="PROCESS")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "payment.running", "RUNNING", "Posting payment and generating ERA")

    era = generate_era_835(submission_id, float(mapped_claim.get("total_charge", 0)))
    pipeline["steps"]["paid"] = True
    _set_pipeline_state(mapped_claim, pipeline, "APPROVED", "payment", "COMPLETED", completed=True, metadata={"payment": era})
    pipeline_log("PAYMENT", "Payment completed", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "payment.completed", "COMPLETED", "Payment completed", {"payment": era})
    _mark_step(job, "payment", "COMPLETED")

    mapped_claim["feedback_data"] = {
        "payment_outcome": "PAID",
        "risk_score": denial.get("denial_risk", 0),
        "denial_reason": denial.get("reason"),
        "validation_corrections": validation.get("corrections", []),
    }
    _mark_step(job, "learning", "RUNNING")
    _set_pipeline_state(mapped_claim, pipeline, "LEARNING", "learning", "RUNNING", metadata={"feedback_data": mapped_claim["feedback_data"]})
    pipeline_log("LEARNING", "Learning running", claim_id=claim_id, submission_id=submission_id, status="START")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "learning.running", "RUNNING", "Capturing payment outcome and learning denial patterns")
    _schedule_pipeline_record_save(mapped_claim, "LEARNING", pipeline, validation=validation, clearinghouse=ch_response, denial=denial, payment=era)
    learning_state = await LearningAgent().run(mapped_claim)
    mapped_claim = learning_state.get("claim", mapped_claim)
    pipeline["steps"]["learning_updated"] = True
    _set_pipeline_state(mapped_claim, pipeline, "LEARNING_COMPLETED", "learning", "COMPLETED", completed=True, metadata={"learning": learning_state})
    _mark_step(job, "learning", "COMPLETED")
    pipeline_log("LEARNING", "Learning completed", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "learning.completed", "COMPLETED", "Learning completed", {"learning": learning_state})
    _schedule_pipeline_record_save(mapped_claim, "LEARNING_COMPLETED", pipeline, validation=validation, clearinghouse=ch_response, denial=denial, payment=era)

    _mark_step(job, "analytics", "RUNNING")
    _set_pipeline_state(mapped_claim, pipeline, "ANALYTICS", "analytics", "RUNNING", metadata={"current_task": "Aggregating orchestration telemetry"})
    pipeline_log("ANALYTICS", "Analytics running", claim_id=claim_id, submission_id=submission_id, status="START")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "analytics.running", "RUNNING", "Aggregating orchestration telemetry and SLA metrics")
    _schedule_pipeline_record_save(mapped_claim, "ANALYTICS", pipeline, validation=validation, clearinghouse=ch_response, denial=denial, payment=era)
    analytics_state = await AnalyticsAgent().run(mapped_claim)
    mapped_claim = analytics_state.get("claim", mapped_claim)
    pipeline["steps"]["analytics_done"] = True
    _set_pipeline_state(mapped_claim, pipeline, "ANALYTICS_COMPLETED", "analytics", "COMPLETED", completed=True, metadata={"analytics": analytics_state})
    _mark_step(job, "analytics", "COMPLETED")
    pipeline_log("ANALYTICS", "Analytics completed", claim_id=claim_id, submission_id=submission_id, status="SUCCESS")
    await _broadcast_realtime_stage(mapped_claim, pipeline, "analytics.completed", "COMPLETED", "Analytics completed", {"analytics": analytics_state})
    _schedule_pipeline_record_save(mapped_claim, "ANALYTICS_COMPLETED", pipeline, validation=validation, clearinghouse=ch_response, denial=denial, payment=era)

    if skip_validation:
        existing_case = mapped_claim.get("case")
        if isinstance(existing_case, dict):
            existing_case["status"] = "CLOSED"

    mapped_claim["status"] = "COMPLETED"
    mapped_claim["pipeline_state"] = "COMPLETED"
    mapped_claim["pipeline_status"] = "COMPLETED"
    mapped_claim["current_stage"] = "COMPLETED"
    mapped_claim["current_agent"] = "NONE"
    mapped_claim["active_step"] = "completed"
    mapped_claim["progress"] = 100
    mapped_claim["finalized_at"] = _utc_now()
    pipeline["pipeline_state"] = "COMPLETED"
    pipeline["pipeline_status"] = "COMPLETED"
    pipeline["current_stage"] = "COMPLETED"
    pipeline["current_agent"] = "NONE"
    pipeline["active_step"] = "completed"
    pipeline["progress"] = 100
    mapped_claim["payment_amount"] = era.get("paid_amount") or era.get("amount") or mapped_claim.get("total_charge", 0)

    duration_seconds = 0.0
    for entry in mapped_claim.get("stage_history", []):
        if not isinstance(entry, dict):
            continue
        try:
            duration_seconds += float(entry.get("duration_seconds") or 0)
        except (TypeError, ValueError):
            continue
    mapped_claim["processing_duration"] = round(duration_seconds, 3)
    mapped_claim["audit_history"] = mapped_claim.get("stage_history", [])
    mapped_claim["cms1500_pdf_url"] = f"/api/claims/{mapped_claim.get('claim_id')}/cms1500"
    mapped_claim["ub04_pdf_url"] = f"/api/claims/{mapped_claim.get('claim_id')}/ub04"
    mapped_claim["edi_url"] = f"/api/claims/{mapped_claim.get('claim_id')}/edi"

    await manager.broadcast({
        "type": "pipeline_completed",
        "event": "pipeline_completed",
        "claim_id": mapped_claim.get("claim_id"),
        "status": "COMPLETED",
        "progress": 100,
        "current_stage": "COMPLETED",
        "current_agent": "NONE",
        "active_step": "completed",
        "claim": mapped_claim,
        "pipeline": pipeline,
        "payment": era,
        "timestamp": _utc_now(),
    })

    mapped_claim["workspace"] = "COMMAND_CENTER"
    mapped_claim["status"] = "PAID"
    mapped_claim["pipeline_state"] = "COMPLETED"
    await manager.broadcast({
        "type": "claim_completed",
        "event": "claim_completed",
        "claim_id": mapped_claim.get("claim_id"),
        "workspace": "COMMAND_CENTER",
        "status": "PAID",
        "progress": 100,
        "current_stage": "COMPLETED",
        "current_agent": "NONE",
        "active_step": "completed",
        "claim": mapped_claim,
        "pipeline": pipeline,
        "payment": era,
        "timestamp": _utc_now(),
    })

    record = _build_pipeline_record(
        mapped_claim,
        "PAID",
        pipeline,
        validation=validation,
        case=mapped_claim.get("case"),
        clearinghouse=ch_response,
        denial=denial,
        payment=era,
    )
    _schedule_pipeline_record_save(
        mapped_claim,
        "PAID",
        pipeline,
        validation=validation,
        case=mapped_claim.get("case"),
        clearinghouse=ch_response,
        denial=denial,
        payment=era,
    )

    return {
        "claim_id": mapped_claim.get("claim_id"),
        "status": "PAID",
        "record": record,
        "pipeline": pipeline,
        "claim": mapped_claim,
    }

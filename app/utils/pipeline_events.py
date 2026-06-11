from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_step_key(value):
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "extract": "ocr",
        "extraction": "ocr",
        "document_processing": "ocr",
        "intake": "ocr",
        "ocr": "ocr",

        "eligibility": "eligibility",

        "validate": "validation",
        "validation": "validation",
        "rules": "validation",
        "rules_validation": "validation",

        "compliance": "compliance",
        "case_orchestrator": "compliance",
        "case_orchestration": "compliance",

        "submit": "submission",
        "submitted": "submission",
        "submission": "submission",

        "clearinghouse": "clearinghouse",
        "clearing_house": "clearinghouse",
        "pending_clearinghouse": "clearinghouse",
        "waiting_for_approval": "clearinghouse",
        "clearinghouse_review": "clearinghouse",

        "ack": "acknowledgment",
        "acknowledged": "acknowledgment",
        "acknowledgment": "acknowledgment",
        "acknowledgement": "acknowledgment",
        "payer_ack": "acknowledgment",
        "payer_acknowledgment": "acknowledgment",
        "payer_acknowledgement": "acknowledgment",

        "denial": "denial_ai",
        "denial_ai": "denial_ai",
        "denial_analysis": "denial_ai",
        "denial_checked": "denial_ai",

        "payment": "payment",
        "paid": "payment",
        "payment_posting": "payment",
        "payment_completed": "payment",

        "learning": "learning",
        "learning_updated": "learning",
        "feedback": "learning",
        "feedback_captured": "learning",

        "analytics": "analytics",
        "analytics_done": "analytics",
        "finish": "analytics",
        "completed": "analytics",
    }

    return aliases.get(raw, raw)


def normalize_status(value):
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def is_clearinghouse_wait(stage, status, pipeline_state=None):
    stage_norm = normalize_status(stage)
    status_norm = normalize_status(status)
    pipeline_state_norm = normalize_status(pipeline_state)

    return (
        stage_norm == "CLEARINGHOUSE"
        and (
            status_norm in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE"}
            or pipeline_state_norm in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE"}
        )
    )


def build_stage_status(step_key, status):
    status_norm = normalize_status(status)

    stage_status = {
        "OCR": "PENDING",
        "ELIGIBILITY": "PENDING",
        "VALIDATION": "PENDING",
        "COMPLIANCE": "PENDING",
        "SUBMISSION": "PENDING",
        "CLEARINGHOUSE": "PENDING",
        "ACKNOWLEDGMENT": "PENDING",
        "DENIAL_AI": "PENDING",
        "PAYMENT": "PENDING",
        "LEARNING": "PENDING",
        "ANALYTICS": "PENDING",
    }

    step_to_stage = {
        "ocr": "OCR",
        "eligibility": "ELIGIBILITY",
        "validation": "VALIDATION",
        "compliance": "COMPLIANCE",
        "submission": "SUBMISSION",
        "clearinghouse": "CLEARINGHOUSE",
        "acknowledgment": "ACKNOWLEDGMENT",
        "denial_ai": "DENIAL_AI",
        "payment": "PAYMENT",
        "learning": "LEARNING",
        "analytics": "ANALYTICS",
    }

    order = [
        "OCR",
        "ELIGIBILITY",
        "VALIDATION",
        "COMPLIANCE",
        "SUBMISSION",
        "CLEARINGHOUSE",
        "ACKNOWLEDGMENT",
        "DENIAL_AI",
        "PAYMENT",
        "LEARNING",
        "ANALYTICS",
    ]

    current_stage = step_to_stage.get(step_key)

    if current_stage in order:
        current_index = order.index(current_stage)

        for index, stage_name in enumerate(order):
            if index < current_index:
                stage_status[stage_name] = "COMPLETED"
            elif index == current_index:
                stage_status[stage_name] = status_norm or "RUNNING"

    return stage_status


def build_pipeline_event(
    *,
    claim_id,
    stage,
    status,
    progress=None,
    current_stage=None,
    current_agent=None,
    active_step=None,
    pipeline_state=None,
    pipeline_status=None,
    review_required=False,
    approval_required=False,
    pipeline_paused=False,
    message=None,
    claim=None,
    extra=None,
):
    step_key = normalize_step_key(active_step or stage or current_stage)
    now = utc_now_iso()

    current_stage = current_stage or stage
    current_agent = current_agent or stage
    active_step = step_key

    if is_clearinghouse_wait(current_stage, status, pipeline_state):
        status = "WAITING_FOR_APPROVAL"
        current_stage = "CLEARINGHOUSE"
        current_agent = "CLEARINGHOUSE"
        active_step = "clearinghouse"
        pipeline_state = "WAITING_FOR_APPROVAL"
        pipeline_status = "WAITING_FOR_APPROVAL"
        review_required = True
        approval_required = True
        pipeline_paused = True
        progress = 70 if progress is None else progress
        step_key = "clearinghouse"
    else:
        pipeline_state = pipeline_state or f"{str(current_stage).upper()}_{str(status).upper()}"
        pipeline_status = pipeline_status or status

    step_payload = {
        "status": status,
        "stage": current_stage,
        "agent": current_agent,
        "progress": progress,
        "message": message or status,
        "updated_at": now,
    }

    stage_status = build_stage_status(step_key, status)

    if step_key == "clearinghouse" and normalize_status(status) == "WAITING_FOR_APPROVAL":
        stage_status.update(
            {
                "OCR": "COMPLETED",
                "ELIGIBILITY": "COMPLETED",
                "VALIDATION": "COMPLETED",
                "COMPLIANCE": "COMPLETED",
                "SUBMISSION": "COMPLETED",
                "CLEARINGHOUSE": "WAITING_FOR_APPROVAL",
                "ACKNOWLEDGMENT": "PENDING",
                "DENIAL_AI": "PENDING",
                "PAYMENT": "PENDING",
                "LEARNING": "PENDING",
                "ANALYTICS": "PENDING",
            }
        )

    payload = {
        "type": "agent_update",
        "event": "agent_update",
        "claim_id": claim_id,
        "stage": current_stage,
        "status": status,
        "progress": progress,
        "current_stage": current_stage,
        "current_agent": current_agent,
        "active_step": active_step,
        "pipeline_state": pipeline_state,
        "pipeline_status": pipeline_status,
        "review_required": review_required,
        "approval_required": approval_required,
        "pipeline_paused": pipeline_paused,
        "timestamp": now,
        "updated_at": now,
        "message": message or status,
        "pipeline": {
            "claim_id": claim_id,
            "current_stage": current_stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "progress": progress,
            "review_required": review_required,
            "approval_required": approval_required,
            "pipeline_paused": pipeline_paused,
            "stage_status": stage_status,
            "steps": {
                step_key: step_payload,
            },
            "updated_at": now,
        },
    }

    if claim is not None:
        payload["claim"] = claim

    if isinstance(extra, dict):
        payload.update(extra)

    return payload


def merge_pipeline_steps(existing, patch):
    steps = {}

    if isinstance(existing, dict):
        steps.update(existing)

    if isinstance(patch, dict):
        for key, value in patch.items():
            if isinstance(steps.get(key), dict) and isinstance(value, dict):
                merged = dict(steps[key])
                merged.update(value)
                steps[key] = merged
            else:
                steps[key] = value

    return steps


def merge_stage_status(existing, patch):
    stage_status = {}

    if isinstance(existing, dict):
        stage_status.update(existing)

    if isinstance(patch, dict):
        stage_status.update(patch)

    return stage_status


def apply_pipeline_patch(claim, **event_kwargs):
    claim = claim or {}

    # Critical safety:
    # apply_pipeline_patch(claim, claim=claim) causes:
    # TypeError: got multiple values for argument 'claim'
    event_claim = event_kwargs.pop("claim", None)

    payload = build_pipeline_event(
        claim=event_claim or claim,
        **event_kwargs,
    )

    pipeline_patch = payload["pipeline"]

    claim.update(
        {
            "status": payload["status"],
            "stage": payload["stage"],
            "current_stage": payload["current_stage"],
            "current_agent": payload["current_agent"],
            "active_step": payload["active_step"],
            "pipeline_state": payload["pipeline_state"],
            "pipeline_status": payload["pipeline_status"],
            "progress": payload["progress"],
            "review_required": payload["review_required"],
            "approval_required": payload["approval_required"],
            "pipeline_paused": payload["pipeline_paused"],
            "updated_at": payload["updated_at"],
            "last_activity_at": payload["updated_at"],
        }
    )

    pipeline = claim.setdefault("pipeline", {})
    existing_steps = pipeline.get("steps") if isinstance(pipeline, dict) else {}
    existing_stage_status = pipeline.get("stage_status") if isinstance(pipeline, dict) else {}

    pipeline.update(
        {
            key: value
            for key, value in pipeline_patch.items()
            if key not in {"steps", "stage_status"}
        }
    )

    pipeline["steps"] = merge_pipeline_steps(
        existing_steps,
        pipeline_patch.get("steps"),
    )

    pipeline["stage_status"] = merge_stage_status(
        existing_stage_status,
        pipeline_patch.get("stage_status"),
    )

    payload["claim"] = claim
    payload["pipeline"] = pipeline

    return payload


async def send_pipeline_event(
    manager,
    *,
    topic,
    action,
    claim_id,
    stage,
    status,
    progress=None,
    current_stage=None,
    current_agent=None,
    active_step=None,
    pipeline_state=None,
    pipeline_status=None,
    review_required=False,
    approval_required=False,
    pipeline_paused=False,
    message=None,
    claim=None,
    extra=None,
):
    event_kwargs = {
        "claim_id": claim_id,
        "stage": stage,
        "status": status,
        "progress": progress,
        "current_stage": current_stage,
        "current_agent": current_agent,
        "active_step": active_step,
        "pipeline_state": pipeline_state,
        "pipeline_status": pipeline_status,
        "review_required": review_required,
        "approval_required": approval_required,
        "pipeline_paused": pipeline_paused,
        "message": message,
        "extra": extra,
    }

    # Do NOT include "claim" in event_kwargs when passing claim positionally.
    # That was the root cause of:
    # apply_pipeline_patch() got multiple values for argument 'claim'
    if claim is not None:
        payload = apply_pipeline_patch(claim, **event_kwargs)
    else:
        payload = build_pipeline_event(**event_kwargs)

    await manager.send_event(topic, action, payload)
    return payload
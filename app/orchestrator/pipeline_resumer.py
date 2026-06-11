# ehr_pipeline/app/orchestrator/pipeline_resumer.py

from datetime import datetime
from typing import Any, Dict, Optional

from app.intake.db_service import get_all_records, update_claim_data


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_record_by_case_id(case_id: str) -> Optional[Dict[str, Any]]:
    records = get_all_records()

    for record in records:
        payload = _safe_dict(record.get("payload"))
        record_case = _safe_dict(record.get("case"))
        payload_case = _safe_dict(payload.get("case"))

        case = record_case or payload_case

        if case.get("case_id") == case_id:
            return record

    return None


def _append_history(case: Dict[str, Any], action: str, details: Dict[str, Any]) -> None:
    case.setdefault("history", [])

    case["history"].append({
        "action": action,
        "timestamp": utc_now(),
        **details,
    })


async def resume_pipeline(case_id: str) -> Dict[str, Any]:
    """
    Resume a paused claim pipeline after a case is reviewed/resolved.

    Used by webhook/case approval flows.
    """

    print(f"🔄 Resuming pipeline for case: {case_id}")

    if not case_id:
        return {
            "status": "FAILED",
            "message": "case_id is required",
            "case_id": case_id,
        }

    record = _find_record_by_case_id(case_id)

    if not record:
        return {
            "status": "NOT_FOUND",
            "message": "No claim record found for case_id",
            "case_id": case_id,
        }

    now = utc_now()

    payload = _safe_dict(record.get("payload"))
    claim = _safe_dict(record.get("claim")) or _safe_dict(payload.get("claim"))
    case = _safe_dict(record.get("case")) or _safe_dict(payload.get("case"))
    pipeline = _safe_dict(record.get("pipeline")) or _safe_dict(payload.get("pipeline"))

    claim_id = (
        record.get("claim_id")
        or claim.get("claim_id")
        or payload.get("claim_id")
    )

    if not claim_id:
        return {
            "status": "FAILED",
            "message": "Could not resolve claim_id for case",
            "case_id": case_id,
        }

    pipeline.setdefault("steps", {})

    case["status"] = "RESOLVED"
    case["resolved_at"] = now
    case["pipeline_resumed"] = True

    _append_history(
        case,
        "PIPELINE_RESUMED",
        {
            "case_id": case_id,
            "claim_id": claim_id,
            "message": "Pipeline resumed after case review",
        },
    )

    claim["status"] = "RESUMED"
    claim["pipeline_state"] = "RESUMED"
    claim["pipeline_status"] = "RESUMED"
    claim["pipeline_paused"] = False
    claim["review_required"] = False
    claim["approval_required"] = False
    claim["resumed_at"] = now
    claim["case_resolved"] = True

    pipeline["pipeline_paused"] = False
    pipeline["resumed_at"] = now
    pipeline["current_stage"] = pipeline.get("current_stage") or "SUBMISSION"
    pipeline["current_agent"] = pipeline.get("current_agent") or "SubmissionAgent"
    pipeline["active_step"] = pipeline.get("active_step") or "submission"
    pipeline["pipeline_status"] = "RESUMED"

    pipeline["steps"]["case_resolved"] = True
    pipeline["steps"]["pipeline_resumed"] = True

    payload["claim"] = claim
    payload["case"] = case
    payload["pipeline"] = pipeline
    payload["status"] = "RESUMED"
    payload["updated_at"] = now

    update_claim_data(
        claim_id,
        {
            "status": "RESUMED",
            "claim": claim,
            "case": case,
            "pipeline": pipeline,
            "payload": payload,
            "updated_at": now,
        },
    )

    return {
        "status": "RESUMED",
        "message": "Pipeline resumed",
        "case_id": case_id,
        "claim_id": claim_id,
        "next_agent": pipeline["current_agent"],
        "next_step": pipeline["active_step"],
        "resumed_at": now,
        "pipeline": pipeline,
        "case": case,
    }
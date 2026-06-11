import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.utils.event_deduplicator import should_emit
from app.utils.event_normalizer import normalize_event
from app.utils.pipeline_events import (
    build_pipeline_event,
    merge_pipeline_steps,
    normalize_step_key,
)
from app.utils.security import mask_sensitive_payload

logger = logging.getLogger(__name__)


INVALID_CLAIM_IDS = {
    "",
    "none",
    "null",
    "undefined",
    "unknown",
}


CLAIM_SCOPED_EVENT_TYPES = {
    "agent_update",
    "pipeline_update",
    "claim_created",
    "claim_updated",
    "claim_processing",
    "claim_completed",
    "claim_deleted",
    "claim_status_updated",
    "clearinghouse_queued",
    "clearinghouse_accepted",
    "clearinghouse_auto_accepted",
    "auto_review_manual_required",
    "clearinghouse_rejected",
    "denial_detected",
    "payment_completed",
    "payment.completed",
    "claim_resubmitted",
    "pipeline_paused",
    "pipeline_resumed",
    "manual_review_required",
    "hitl_approved",
    "case_created",
    "case_escalated",
    "case_assigned",
}


NON_BATCHABLE_BULK_EVENTS = {
    "agent_update",
    "bulk_progress",
    "bulk_upload_started",
    "bulk_upload_queued",
    "bulk_upload_completed",
    "bulk_upload_failed",
}


def _clean_claim_id(value: Any) -> str:
    claim_id = str(value or "").strip()
    return "" if claim_id.lower() in INVALID_CLAIM_IDS else claim_id


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _nested_value(source: Dict[str, Any], key: str) -> Any:
    if not isinstance(source, dict) or not key:
        return None

    current = source

    for segment in key.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(segment)

        if current is None:
            return None

    return current


def _source_candidates(source: Any) -> list[Dict[str, Any]]:
    source = _dict_or_empty(source)

    raw_event = _dict_or_empty(source.get("rawEvent"))
    payload = _dict_or_empty(source.get("payload"))
    details = _dict_or_empty(source.get("details"))
    data = _dict_or_empty(source.get("data"))
    metadata = _dict_or_empty(source.get("metadata"))
    claim = _dict_or_empty(source.get("claim"))

    return [
        source,
        claim,
        raw_event,
        payload,
        details,
        data,
        metadata,
        _dict_or_empty(data.get("details")),
        _dict_or_empty(data.get("claim")),
        _dict_or_empty(payload.get("claim")),
        _dict_or_empty(raw_event.get("claim")),
        _dict_or_empty(details.get("claim")),
        _dict_or_empty(source.get("snapshot")),
        _dict_or_empty(source.get("pipeline")),
        _dict_or_empty(source.get("agent_event")),
        _dict_or_empty(_dict_or_empty(source.get("agent_event")).get("metrics")),
    ]


def _read_first(source: Any, *keys: str) -> Any:
    for candidate in _source_candidates(source):
        for key in keys:
            value = _nested_value(candidate, key)

            if value is not None and value != "":
                return value

    return None


def _has_payload_value(value: Any, visited=None, depth: int = 0) -> bool:
    """
    Check whether a value has meaningful payload data.
    Includes circular-reference and depth protection.
    """
    if depth > 8:
        return False

    if visited is None:
        visited = set()

    obj_id = id(value)

    if obj_id in visited:
        return False

    visited.add(obj_id)

    if value is None:
        return False

    if isinstance(value, bool):
        return True

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        return value.strip() != ""

    if isinstance(value, dict):
        return any(
            _has_payload_value(item, visited, depth + 1)
            for item in value.values()
        )

    if isinstance(value, (list, tuple, set)):
        return any(
            _has_payload_value(item, visited, depth + 1)
            for item in value
        )

    return True


def _claim_summary_has_data(summary: Dict[str, Any]) -> bool:
    ignored = {
        "fields_extracted",
        "extracted_fields_count",
    }

    return any(
        _has_payload_value(value)
        for key, value in summary.items()
        if key not in ignored
    )


def _merge_claim_summary(
    previous: Dict[str, Any],
    current: Dict[str, Any],
    depth: int = 0,
    visited=None,
) -> Dict[str, Any]:
    """
    Safely merge claim summaries without following circular/deep references.
    WebSocket payloads may contain nested claim/pipeline/details objects.
    """
    if visited is None:
        visited = set()

    if depth > 6:
        return dict(current or {})

    if not isinstance(previous, dict):
        previous = {}

    if not isinstance(current, dict):
        current = {}

    current_id = id(current)
    previous_id = id(previous)

    if current_id in visited or previous_id in visited:
        return dict(current or {})

    visited.add(current_id)
    visited.add(previous_id)

    result = dict(current or {})

    # Never recursively merge these heavy/deep keys.
    skip_deep_keys = {
        "claim",
        "payload",
        "data",
        "details",
        "rawEvent",
        "raw_event",
        "pipeline",
        "agent_event",
        "event_history",
        "history",
        "input",
        "output",
        "response",
        "request",
        "metadata",
        "stage_history",
    }

    for key, previous_value in (previous or {}).items():
        if key in skip_deep_keys:
            if key not in result and _has_payload_value(previous_value):
                result[key] = previous_value
            continue

        current_value = result.get(key)

        if isinstance(previous_value, dict) and isinstance(current_value, dict):
            result[key] = _merge_claim_summary(
                previous_value,
                current_value,
                depth=depth + 1,
                visited=visited,
            )

        elif not _has_payload_value(current_value) and _has_payload_value(previous_value):
            result[key] = previous_value

    return result


def _extract_best_claim_source(source: Any) -> Dict[str, Any]:
    """
    Finds the richest claim-like object from an event payload.

    Agents may send:
    - data directly as claim
    - data["claim"]
    - data["data"]["claim"]
    - data["payload"]["claim"]
    - data["details"]["claim"]
    """

    source = _dict_or_empty(source)

    candidates = [
        _dict_or_empty(source.get("claim")),
        _dict_or_empty(_dict_or_empty(source.get("data")).get("claim")),
        _dict_or_empty(_dict_or_empty(source.get("payload")).get("claim")),
        _dict_or_empty(_dict_or_empty(source.get("details")).get("claim")),
        source,
    ]

    best = {}

    for candidate in candidates:
        summary = _agent_claim_summary(candidate)

        if _claim_summary_has_data(summary):
            if len(str(candidate)) > len(str(best)):
                best = candidate

    return best or source


def _agent_claim_summary(source: Any) -> Dict[str, Any]:
    provider = _read_first(source, "provider", "claim.provider") or {}
    insurance = _read_first(source, "insurance", "claim.insurance") or {}
    coverage = _read_first(source, "coverage", "claim.coverage") or {}
    payer_obj = _read_first(source, "payer", "claim.payer") or {}

    provider = provider if isinstance(provider, dict) else {}
    insurance = insurance if isinstance(insurance, dict) else {}

    if isinstance(payer_obj, dict):
        payer_obj = payer_obj
    elif payer_obj:
        payer_obj = {"name": payer_obj}
    else:
        payer_obj = {}

    if isinstance(coverage, dict):
        normalized_coverage = coverage
    elif coverage:
        normalized_coverage = {
            "status": coverage,
            "active": coverage,
        }
    else:
        normalized_coverage = {}

    extracted_fields = (
        _read_first(
            source,
            "extracted_fields",
            "fields",
            "extraction.extracted_fields",
            "claim.extracted_fields",
            "claim.extraction.extracted_fields",
        )
        or {}
    )

    extracted_fields = (
        extracted_fields
        if isinstance(extracted_fields, (dict, list))
        else {}
    )

    missing_fields = (
        _read_first(
            source,
            "missing_fields",
            "missing_mapped_fields",
            "validation.missing_fields",
            "claim.missing_fields",
            "claim.validation.missing_fields",
        )
        or []
    )

    if not isinstance(missing_fields, list):
        missing_fields = [missing_fields]

    file_name = _read_first(
        source,
        "filename",
        "file_name",
        "document.file_name",
        "document.filename",
        "source_file.filename",
        "source_file.key",
        "claim.filename",
        "claim.file_name",
        "claim.source_file.filename",
        "claim.source_file.key",
    )

    total_pages = _read_first(
        source,
        "total_pages",
        "pages",
        "page_count",
        "document.total_pages",
        "document.pages",
        "extraction.page_count",
        "claim.total_pages",
        "claim.extraction.page_count",
    )

    document_type = _read_first(
        source,
        "document_type",
        "doc_type",
        "claim_type",
        "form_type",
        "document.document_type",
        "claim.document_type",
        "claim.form_type",
        "claim.claim_type",
    )

    extracted_count = (
        len(extracted_fields)
        if isinstance(extracted_fields, (dict, list))
        else 0
    )

    services = _read_first(
        source,
        "services",
        "claim.services",
    ) or []

    if not isinstance(services, list):
        services = []

    payer_name = _first_value(
        payer_obj.get("name"),
        _read_first(
            source,
            "payer.name",
            "payer_name",
            "insurance.payer",
            "insurance.payer_name",
            "claim.payer.name",
            "claim.payer_name",
            "claim.insurance.payer",
            "claim.insurance.payer_name",
        ),
        insurance.get("payer"),
    )

    return {
        "claim_id": _read_first(
            source,
            "claim_id",
            "claim.claim_id",
            "data.claim_id",
            "payload.claim_id",
        ),

        "patient_name": _read_first(
            source,
            "patient_name",
            "patient.name",
            "claim.patient.name",
            "extracted_fields.patient_name",
            "claim.extracted_fields.patient_name",
        ),
        "patient_dob": _read_first(
            source,
            "patient_dob",
            "patient.dob",
            "dob",
            "claim.patient.dob",
            "claim.dob",
            "extracted_fields.patient_dob",
            "claim.extracted_fields.patient_dob",
        ),

        "file_name": file_name,
        "filename": file_name,
        "total_pages": total_pages,
        "document_type": document_type,
        "form_type": _read_first(source, "form_type", "claim.form_type"),

        "payer": payer_obj or {"name": payer_name},
        "payer_name": payer_name,
        "payer_id": _first_value(
            payer_obj.get("payer_id"),
            payer_obj.get("id"),
            _read_first(
                source,
                "payer_id",
                "payer.payer_id",
                "payer.id",
                "claim.payer_id",
                "claim.payer.payer_id",
                "claim.payer.id",
            ),
        ),

        "member_id": _first_value(
            _read_first(
                source,
                "member_id",
                "subscriber_id",
                "insurance.member_id",
                "insurance.subscriber_id",
                "patient.member_id",
                "claim.member_id",
                "claim.insurance.member_id",
                "claim.insurance.subscriber_id",
                "claim.patient.member_id",
            ),
            insurance.get("member_id"),
        ),

        "provider": provider,
        "provider_name": _first_value(
            provider.get("name"),
            _read_first(
                source,
                "provider.name",
                "provider_name",
                "claim.provider.name",
                "claim.provider_name",
            ),
        ),
        "provider_npi": _first_value(
            provider.get("npi"),
            _read_first(
                source,
                "provider.npi",
                "provider_npi",
                "claim.provider.npi",
                "claim.provider_npi",
            ),
        ),

        "insurance": insurance,
        "coverage": normalized_coverage,
        "active_coverage": _first_value(
            _read_first(
                source,
                "active_coverage",
                "coverage_active",
                "coverage.active",
                "claim.active_coverage",
                "claim.coverage.active",
            ),
            normalized_coverage.get("active"),
        ),
        "eligibility_status": _first_value(
            _read_first(
                source,
                "eligibility_status",
                "coverage_status",
                "coverage.status",
                "claim.eligibility_status",
                "claim.coverage.status",
            ),
            normalized_coverage.get("status"),
        ),

        "ocr_quality": _read_first(
            source,
            "ocr_quality",
            "ocr_confidence",
            "quality_score",
            "extraction.ocr_quality",
            "extraction.ocr_confidence",
            "extraction.extraction_confidence",
            "claim.ocr_quality",
            "claim.ocr_confidence",
            "claim.extraction_confidence",
            "claim.extraction.extraction_confidence",
        ),
        "validation_score": _read_first(
            source,
            "validation_score",
            "score",
            "validation.validation_score",
            "validation.score",
            "claim.validation_score",
            "claim.validation.validation_score",
            "claim.validation.score",
        ),
        "risk_score": _read_first(
            source,
            "risk_score",
            "denial_risk",
            "risk.score",
            "validation.risk_score",
            "compliance.risk_score",
            "claim.risk_score",
            "claim.validation.risk_score",
            "claim.compliance.risk_score",
        ),
        "confidence": _read_first(
            source,
            "confidence",
            "ai_confidence",
            "ocr_confidence",
            "extraction.confidence",
            "extraction.extraction_confidence",
            "claim.confidence",
            "claim.extraction_confidence",
            "claim.extraction.confidence",
            "claim.extraction.extraction_confidence",
        ),

        "cpt_codes": _read_first(
            source,
            "cpt_codes",
            "cpt",
            "medical_coding.cpt",
            "extracted_fields.cpt_codes",
            "claim.cpt_codes",
            "claim.medical_coding.cpt",
            "claim.extracted_fields.cpt_codes",
        ) or [],
        "icd_codes": _read_first(
            source,
            "icd_codes",
            "icd",
            "diagnosis_codes",
            "medical_coding.icd",
            "extracted_fields.icd_codes",
            "claim.icd_codes",
            "claim.diagnosis_codes",
            "claim.medical_coding.icd",
            "claim.extracted_fields.icd_codes",
        ) or [],

        "services": services,
        "service_count": len(services),
        "total_charge": _read_first(
            source,
            "total_charge",
            "claim.total_charge",
        ),

        "missing_fields": missing_fields,
        "extracted_fields": extracted_fields,
        "fields_extracted": extracted_count,
        "extracted_fields_count": extracted_count,

        "ai_suggestions": _read_first(
            source,
            "ai_suggestions",
            "suggestions",
            "recommendations",
            "claim.ai_suggestions",
            "claim.suggestions",
            "claim.recommendations",
        ) or [],
        "suggestions": _read_first(
            source,
            "suggestions",
            "recommendations",
            "ai_suggestions",
            "claim.suggestions",
            "claim.recommendations",
            "claim.ai_suggestions",
        ) or [],

        "document": {
            "file_name": file_name,
            "total_pages": total_pages,
            "document_type": document_type,
            "source_file": _read_first(
                source,
                "source_file",
                "claim.source_file",
            ) or {},
        },
    }


def _agent_metrics(source: Any) -> Dict[str, Any]:
    metrics = _read_first(source, "metrics") or {}
    metrics = metrics if isinstance(metrics, dict) else {}

    return {
        "cpu": _first_value(
            metrics.get("cpu"),
            _read_first(source, "cpu", "cpu_usage", "metrics.cpu"),
        ),
        "memory": _first_value(
            metrics.get("memory"),
            _read_first(source, "memory", "memory_usage", "metrics.memory"),
        ),
        "latency": _first_value(
            metrics.get("latency"),
            _read_first(source, "latency", "latency_ms", "metrics.latency"),
        ),
        "tokens": _first_value(
            metrics.get("tokens"),
            _read_first(source, "tokens", "token_count", "metrics.tokens"),
        ),
    }



def _normalize_stage_key(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _stage_defaults(stage: Any, status: Any = None) -> Dict[str, Any]:
    stage_key = _normalize_stage_key(stage)
    status_key = _normalize_stage_key(status)

    step_map = {
        "EXTRACT": "ocr",
        "EXTRACTION": "ocr",
        "OCR": "ocr",
        "ELIGIBILITY": "eligibility",
        "VALIDATION": "validation",
        "COMPLIANCE": "compliance",
        "SUBMISSION": "submission",
        "CLEARINGHOUSE": "clearinghouse",
        "ACKNOWLEDGMENT": "acknowledgment",
        "PAYER_ACKNOWLEDGMENT": "acknowledgment",
        "PAYER": "payer",
        "DENIAL": "denial_ai",
        "DENIAL_AI": "denial_ai",
        "PAYMENT": "payment",
        "LEARNING": "learning",
        "ANALYTICS": "analytics",
        "FINISH": "analytics",
        "COMPLETED": "analytics",
    }

    agent_map = {
        "EXTRACT": "OCRAgent",
        "EXTRACTION": "OCRAgent",
        "OCR": "OCRAgent",
        "ELIGIBILITY": "EligibilityAgent",
        "VALIDATION": "ValidationAgent",
        "COMPLIANCE": "ComplianceAgent",
        "SUBMISSION": "SubmissionAgent",
        "CLEARINGHOUSE": "CLEARINGHOUSE",
        "ACKNOWLEDGMENT": "PAYER_ACKNOWLEDGMENT",
        "PAYER_ACKNOWLEDGMENT": "PAYER_ACKNOWLEDGMENT",
        "PAYER": "PAYER",
        "DENIAL": "DENIAL_AI",
        "DENIAL_AI": "DENIAL_AI",
        "PAYMENT": "PAYMENT",
        "LEARNING": "LearningAgent",
        "ANALYTICS": "AnalyticsAgent",
        "FINISH": "AnalyticsAgent",
        "COMPLETED": "AnalyticsAgent",
    }

    running_progress = {
        "EXTRACT": 15,
        "EXTRACTION": 15,
        "OCR": 15,
        "ELIGIBILITY": 25,
        "VALIDATION": 40,
        "COMPLIANCE": 55,
        "SUBMISSION": 65,
        "CLEARINGHOUSE": 70,
        "ACKNOWLEDGMENT": 74,
        "PAYER_ACKNOWLEDGMENT": 74,
        "PAYER": 76,
        "DENIAL": 80,
        "DENIAL_AI": 80,
        "PAYMENT": 88,
        "LEARNING": 94,
        "ANALYTICS": 98,
        "FINISH": 100,
        "COMPLETED": 100,
    }

    completed_progress = {
        **running_progress,
        "ELIGIBILITY": 25,
        "VALIDATION": 40,
        "COMPLIANCE": 55,
        "SUBMISSION": 65,
        "CLEARINGHOUSE": 70,
        "DENIAL": 82,
        "DENIAL_AI": 82,
        "PAYMENT": 88,
        "LEARNING": 94,
        "ANALYTICS": 100,
        "FINISH": 100,
        "COMPLETED": 100,
    }

    if status_key in {"COMPLETED", "SUCCESS", "PAID"}:
        progress = completed_progress.get(stage_key, 100)
    else:
        progress = running_progress.get(stage_key, 70)

    return {
        "stage_key": stage_key,
        "active_step": step_map.get(stage_key) or stage_key.lower(),
        "current_agent": agent_map.get(stage_key) or stage_key,
        "progress": progress,
    }


def _normalize_agent_update_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure every agent_update sent to the frontend has a complete live state.

    This fixes UI rows/panels that only update after refresh by preserving and
    filling progress, pipeline_state, current_stage/current_agent, and review
    flags both at the top level and inside payload["claim"].
    """
    data = data or {}

    claim = data.get("claim")
    if not isinstance(claim, dict):
        claim = {}

    pipeline = data.get("pipeline")
    if not isinstance(pipeline, dict):
        pipeline = {}

    stage = (
        data.get("current_stage")
        or data.get("stage")
        or claim.get("current_stage")
        or claim.get("stage")
        or pipeline.get("current_stage")
        or pipeline.get("stage")
        or data.get("agent")
        or "PIPELINE"
    )

    status = (
        data.get("status")
        or claim.get("status")
        or pipeline.get("status")
        or "RUNNING"
    )

    stage_key = _normalize_stage_key(stage)
    status_key = _normalize_stage_key(status)
    defaults = _stage_defaults(stage_key, status_key)

    progress = data.get("progress")
    if progress is None:
        progress = claim.get("progress")
    if progress is None:
        progress = pipeline.get("progress")
    if progress is None:
        progress = defaults["progress"]

    pipeline_state = (
        data.get("pipeline_state")
        or claim.get("pipeline_state")
        or pipeline.get("pipeline_state")
        or data.get("pipeline_status")
        or claim.get("pipeline_status")
        or pipeline.get("pipeline_status")
    )

    if not pipeline_state:
        if status_key in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "PENDING_APPROVAL"}:
            pipeline_state = "WAITING_FOR_APPROVAL"
        elif status_key in {"COMPLETED", "SUCCESS"}:
            pipeline_state = (
                "COMPLETED"
                if stage_key in {"ANALYTICS", "FINISH", "COMPLETED"}
                else f"{stage_key}_COMPLETED"
            )
        elif status_key == "PAID":
            pipeline_state = "COMPLETED"
        else:
            pipeline_state = f"{stage_key}_RUNNING"

    active_step = (
        data.get("active_step")
        or data.get("current_step")
        or claim.get("active_step")
        or claim.get("current_step")
        or pipeline.get("active_step")
        or pipeline.get("current_step")
        or defaults["active_step"]
    )
    active_step = normalize_step_key(active_step)

    current_agent = (
        data.get("current_agent")
        or claim.get("current_agent")
        or pipeline.get("current_agent")
        or defaults["current_agent"]
    )

    if active_step == "ocr":
        stage_key = "OCR"
        current_agent = (
            current_agent
            if current_agent not in {"EXTRACT", "EXTRACTION", "OCR / Extraction"}
            else "OCRAgent"
        )

    if active_step == "compliance" and (
        status_key in {"HITL_REQUIRED", "HARD_REJECT"}
        or stage_key in {"CASE_ORCHESTRATOR", "CASE_ORCHESTRATION"}
    ):
        stage_key = "COMPLIANCE"
        current_agent = "ComplianceAgent"
        if status_key in {"HITL_REQUIRED", "HARD_REJECT"}:
            pipeline_state = status_key

    is_waiting = (
        status_key in {"WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "PENDING_APPROVAL"}
        or _normalize_stage_key(pipeline_state) == "WAITING_FOR_APPROVAL"
    )

    if is_waiting:
        stage_key = "CLEARINGHOUSE"
        status_key = "WAITING_FOR_APPROVAL"
        active_step = "clearinghouse"
        current_agent = "CLEARINGHOUSE"
        progress = 70
        pipeline_state = "WAITING_FOR_APPROVAL"

    if status_key == "PAID" and stage_key == "PAYMENT":
        progress = data.get("progress") or claim.get("progress") or pipeline.get("progress") or 88
        pipeline_state = "PAYMENT_COMPLETED"
    elif status_key == "PAID":
        progress = 100
        pipeline_state = "COMPLETED"

    review_required = (
        data.get("review_required")
        if data.get("review_required") is not None
        else claim.get("review_required")
    )
    approval_required = (
        data.get("approval_required")
        if data.get("approval_required") is not None
        else claim.get("approval_required")
    )
    pipeline_paused = (
        data.get("pipeline_paused")
        if data.get("pipeline_paused") is not None
        else claim.get("pipeline_paused")
    )

    if is_waiting:
        review_required = True
        approval_required = True
        pipeline_paused = True
    if review_required is None:
        review_required = False
    if approval_required is None:
        approval_required = False
    if pipeline_paused is None:
        pipeline_paused = False

    claim_id = _clean_claim_id(data.get("claim_id") or claim.get("claim_id"))
    pipeline_status = (
        data.get("pipeline_status")
        or claim.get("pipeline_status")
        or pipeline.get("pipeline_status")
        or status_key
    )

    if status_key == "PAID" and stage_key == "PAYMENT":
        pipeline_status = "PAID"
    elif status_key == "PAID":
        pipeline_status = "COMPLETED"

    message = (
        data.get("message")
        or claim.get("message")
        or pipeline.get("message")
        or status_key
    )

    canonical_payload = build_pipeline_event(
        claim_id=claim_id,
        stage=stage_key,
        status=status_key,
        progress=progress,
        current_stage=stage_key,
        current_agent=current_agent,
        active_step=active_step,
        pipeline_state=pipeline_state,
        pipeline_status=pipeline_status,
        review_required=bool(review_required),
        approval_required=bool(approval_required),
        pipeline_paused=bool(pipeline_paused),
        message=message,
    )
    canonical_pipeline = canonical_payload["pipeline"]

    claim.update(
        {
            "claim_id": claim_id,
            "status": "PENDING_CLEARINGHOUSE" if is_waiting else claim.get("status", status_key),
            "stage": stage_key,
            "current_stage": stage_key,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "pipeline_result": data.get("pipeline_result") or claim.get("pipeline_result"),
            "progress": progress,
            "review_required": bool(review_required),
            "approval_required": bool(approval_required),
            "pipeline_paused": bool(pipeline_paused),
            "clearinghouse_status": data.get("clearinghouse_status") or claim.get("clearinghouse_status"),
        }
    )

    existing_steps = pipeline.get("steps") if isinstance(pipeline, dict) else {}
    pipeline.update({
        key: value
        for key, value in canonical_pipeline.items()
        if key != "steps"
    })
    pipeline.update({
        "pipeline_result": data.get("pipeline_result") or pipeline.get("pipeline_result"),
        "review_required": bool(review_required),
        "approval_required": bool(approval_required),
        "pipeline_paused": bool(pipeline_paused),
        "clearinghouse_status": data.get("clearinghouse_status") or pipeline.get("clearinghouse_status"),
    })
    pipeline["steps"] = merge_pipeline_steps(
        existing_steps,
        canonical_pipeline.get("steps"),
    )

    data.update(
        {
            "type": "agent_update",
            "event": "agent_update",
            "claim_id": claim_id,
            "stage": stage_key,
            "status": status_key,
            "progress": progress,
            "current_stage": stage_key,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "pipeline_result": claim.get("pipeline_result"),
            "review_required": claim.get("review_required"),
            "approval_required": claim.get("approval_required"),
            "pipeline_paused": claim.get("pipeline_paused"),
            "clearinghouse_status": claim.get("clearinghouse_status"),
            "claim": claim,
            "pipeline": pipeline,
        }
    )

    return data


def emit_agent_event(claim_id, agent, status, stage, details=None):
    claim_id = _clean_claim_id(claim_id)

    if not claim_id:
        logger.error(
            "Missing claim_id for websocket agent event",
            extra={
                "agent": agent,
                "status": status,
                "stage": stage,
            },
        )
        return None

    detail_payload = details if isinstance(details, dict) else {"message": details}
    now = datetime.utcnow().isoformat()

    best_claim_source = _extract_best_claim_source(detail_payload)
    claim_summary = _agent_claim_summary(best_claim_source)

    event = {
        "type": "agent_update",
        "event": "agent_update",
        "claim_id": claim_id,
        "stage": str(stage or agent or ""),
        "status": str(status or "INFO").upper(),
        "progress": detail_payload.get("progress"),
        "current_stage": detail_payload.get("current_stage") or stage or agent,
        "current_agent": detail_payload.get("current_agent") or agent,
        "active_step": (
            detail_payload.get("active_step")
            or detail_payload.get("current_step")
            or stage
            or agent
        ),
        "timestamp": detail_payload.get("timestamp") or now,
        "pipeline_state": detail_payload.get("pipeline_state"),
        "pipeline_status": detail_payload.get("pipeline_status"),
        "pipeline_result": detail_payload.get("pipeline_result"),
        "review_required": detail_payload.get("review_required"),
        "approval_required": detail_payload.get("approval_required"),
        "pipeline_paused": detail_payload.get("pipeline_paused"),
        "clearinghouse_status": detail_payload.get("clearinghouse_status"),
        "payment_status": detail_payload.get("payment_status"),
        "claim": claim_summary,
        "pipeline": _dict_or_empty(detail_payload.get("pipeline")),
        "metrics": _agent_metrics(detail_payload),
    }

    return _normalize_agent_update_payload(event)



class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

        self._bulk_buffers: Dict[str, list] = {}
        self._bulk_flush_tasks: Dict[str, asyncio.Task] = {}
        self._claim_bulk_sessions: Dict[str, str] = {}
        self._claim_snapshots: Dict[str, Dict[str, Any]] = {}

        self._bulk_batch_size = 50
        self._bulk_flush_interval_seconds = 1.0

    def register_bulk_claims(self, bulk_session_id: str, claim_ids):
        if not bulk_session_id:
            return

        for claim_id in claim_ids or []:
            clean_id = _clean_claim_id(claim_id)

            if clean_id:
                self._claim_bulk_sessions[clean_id] = str(bulk_session_id)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[id(websocket)] = websocket

        print(
            f"WS connected | total={len(self.active_connections)}",
            flush=True,
        )

    def disconnect(self, websocket: WebSocket):
        removed = self.active_connections.pop(id(websocket), None)

        if removed:
            print(
                f"WS disconnected | total={len(self.active_connections)}",
                flush=True,
            )

    def _extract_claim_id(self, data: dict) -> str:
        if not isinstance(data, dict):
            return ""

        claim = _dict_or_empty(data.get("claim"))
        payload = _dict_or_empty(data.get("payload"))
        payload_claim = _dict_or_empty(payload.get("claim"))
        details = _dict_or_empty(data.get("details"))
        detail_claim = _dict_or_empty(details.get("claim"))
        nested_data = _dict_or_empty(data.get("data"))
        nested_claim = _dict_or_empty(nested_data.get("claim"))
        metadata = _dict_or_empty(data.get("metadata"))
        pipeline = _dict_or_empty(data.get("pipeline"))

        return _clean_claim_id(
            data.get("claim_id")
            or data.get("claimId")
            or claim.get("claim_id")
            or claim.get("claimId")
            or payload.get("claim_id")
            or payload.get("claimId")
            or payload_claim.get("claim_id")
            or payload_claim.get("claimId")
            or details.get("claim_id")
            or details.get("claimId")
            or detail_claim.get("claim_id")
            or detail_claim.get("claimId")
            or nested_data.get("claim_id")
            or nested_data.get("claimId")
            or nested_claim.get("claim_id")
            or nested_claim.get("claimId")
            or metadata.get("claim_id")
            or metadata.get("claimId")
            or pipeline.get("claim_id")
            or pipeline.get("claimId")
        )

    def _normalize_outbound_event(self, data: dict) -> Optional[dict]:
        if not isinstance(data, dict):
            return data

        def _safe_claim_display_fields(claim: Any) -> Dict[str, Any]:
            claim = _dict_or_empty(claim)

            allowed_claim_keys = [
                "claim_id",
                "claimId",
                "id",
                "status",
                "stage",
                "current_stage",
                "current_agent",
                "active_step",
                "current_step",
                "pipeline_state",
                "pipeline_status",
                "pipeline_result",
                "progress",
                "review_required",
                "approval_required",
                "pipeline_paused",
                "clearinghouse_status",
                "payment_status",
                "patient_name",
                "payer_name",
                "provider_name",
                "member_id",
                "form_type",
                "document_type",
                "claim_type",
                "file_name",
                "filename",
                "source",
                "total_charge",
                "updated_at",
                "updatedAt",
                "last_activity_at",
            ]

            safe_claim = {
                key: claim.get(key)
                for key in allowed_claim_keys
                if claim.get(key) is not None
            }

            # Keep only shallow nested display data.
            # Do not keep nested claim/pipeline/data/details objects.
            for nested_key in ["patient", "payer", "provider", "insurance"]:
                nested_value = claim.get(nested_key)

                if isinstance(nested_value, dict):
                    safe_claim[nested_key] = {
                        key: value
                        for key, value in nested_value.items()
                        if key
                        in {
                            "name",
                            "dob",
                            "member_id",
                            "payer",
                            "payer_name",
                            "npi",
                            "tax_id",
                            "id",
                        }
                        and value is not None
                    }

            return safe_claim

        def _safe_pipeline_display_fields(pipeline: Any) -> Dict[str, Any]:
            pipeline = _dict_or_empty(pipeline)

            allowed_pipeline_keys = [
                "pipeline_state",
                "pipeline_status",
                "pipeline_result",
                "current_stage",
                "current_agent",
                "active_step",
                "current_step",
                "progress",
                "review_required",
                "approval_required",
                "pipeline_paused",
                "clearinghouse_status",
                "payment_status",
                "updated_at",
                "updatedAt",
            ]

            safe_pipeline = {
                key: pipeline.get(key)
                for key in allowed_pipeline_keys
                if pipeline.get(key) is not None
            }

            if isinstance(pipeline.get("steps"), dict):
                safe_pipeline["steps"] = dict(pipeline["steps"])

            if isinstance(pipeline.get("stage_status"), dict):
                safe_pipeline["stage_status"] = dict(pipeline["stage_status"])

            return safe_pipeline

        def _safe_merge_claims(*claims: Any) -> Dict[str, Any]:
            merged: Dict[str, Any] = {}

            for claim in claims:
                safe_claim = _safe_claim_display_fields(claim)

                for key, value in safe_claim.items():
                    if value is not None and value != "":
                        merged[key] = value

            return merged

        event_type = str(data.get("type") or data.get("event") or "").strip()
        normalized_type = event_type.lower()
        claim_id = self._extract_claim_id(data)

        if normalized_type in CLAIM_SCOPED_EVENT_TYPES and not claim_id:
            logger.error(
                "Missing claim_id; websocket event suppressed: %s",
                {
                    "type": data.get("type"),
                    "event": data.get("event"),
                    "stage": data.get("stage"),
                    "status": data.get("status"),
                },
            )
            return None

        if claim_id:
            best_claim_source = _extract_best_claim_source(data)
            claim_summary = _agent_claim_summary(best_claim_source)

            existing_snapshot = self._claim_snapshots.get(claim_id, {})
            existing_claim = data.get("claim")

            safe_claim = _safe_merge_claims(
                existing_snapshot,
                existing_claim,
                claim_summary,
            )

            if _claim_summary_has_data(safe_claim):
                self._claim_snapshots[claim_id] = safe_claim

            data = {
                **data,
                "claim_id": claim_id,
                "timestamp": data.get("timestamp") or datetime.utcnow().isoformat(),
            }

            if normalized_type == "agent_update":
                data["claim"] = safe_claim
            else:
                data = {
                    **data,
                    "details": _dict_or_empty(data.get("details")),
                    "metrics": _dict_or_empty(data.get("metrics")),
                    "warnings": (
                        data.get("warnings")
                        if isinstance(data.get("warnings"), list)
                        else []
                    ),
                }

        if normalized_type == "agent_update":
            data.setdefault("event", "agent_update")
            data.setdefault("type", "agent_update")
            data.setdefault(
                "agent",
                data.get("step") or data.get("stage") or "Pipeline Agent",
            )
            data.setdefault(
                "stage",
                data.get("step") or data.get("agent") or "Pipeline Agent",
            )
            data.setdefault("status", "INFO")

            claim = _safe_claim_display_fields(data.get("claim"))
            pipeline = _safe_pipeline_display_fields(data.get("pipeline"))

            # Preserve top-level live fields inside claim so frontend merge works.
            live_fields = {
                "claim_id": data.get("claim_id") or claim.get("claim_id"),
                "status": data.get("status") or claim.get("status"),
                "stage": data.get("stage") or claim.get("stage"),
                "current_stage": data.get("current_stage")
                or claim.get("current_stage"),
                "current_agent": data.get("current_agent")
                or claim.get("current_agent"),
                "active_step": data.get("active_step") or claim.get("active_step"),
                "pipeline_state": data.get("pipeline_state")
                or claim.get("pipeline_state"),
                "pipeline_status": data.get("pipeline_status")
                or claim.get("pipeline_status"),
                "pipeline_result": data.get("pipeline_result")
                or claim.get("pipeline_result"),
                "progress": (
                    data.get("progress")
                    if data.get("progress") is not None
                    else claim.get("progress")
                ),
                "review_required": (
                    data.get("review_required")
                    if data.get("review_required") is not None
                    else claim.get("review_required")
                ),
                "approval_required": (
                    data.get("approval_required")
                    if data.get("approval_required") is not None
                    else claim.get("approval_required")
                ),
                "pipeline_paused": (
                    data.get("pipeline_paused")
                    if data.get("pipeline_paused") is not None
                    else claim.get("pipeline_paused")
                ),
                "clearinghouse_status": data.get("clearinghouse_status")
                or claim.get("clearinghouse_status"),
                "payment_status": data.get("payment_status")
                or claim.get("payment_status"),
            }

            claim = _safe_merge_claims(claim, live_fields)

            if pipeline:
                data["pipeline"] = pipeline

            data["claim"] = claim

            if _claim_summary_has_data(claim) and data.get("claim_id"):
                self._claim_snapshots[data["claim_id"]] = claim

            data["metrics"] = _agent_metrics(data)

            data = _normalize_agent_update_payload(data)

            # Re-sanitize after normalization in case it added nested objects.
            data["claim"] = _safe_claim_display_fields(data.get("claim"))

            if isinstance(data.get("pipeline"), dict):
                data["pipeline"] = _safe_pipeline_display_fields(
                    data.get("pipeline")
                )

            allowed = {
                "type",
                "event",
                "claim_id",
                "stage",
                "status",
                "progress",
                "current_stage",
                "current_agent",
                "active_step",
                "timestamp",
                "pipeline_state",
                "pipeline_status",
                "pipeline_result",
                "review_required",
                "approval_required",
                "pipeline_paused",
                "clearinghouse_status",
                "payment_status",
                "claim",
                "pipeline",
                "metrics",
                "agent_detail",
            }

            data = {
                key: value
                for key, value in data.items()
                if key in allowed
            }

        return normalize_event(data)

    def _bulk_session_id(self, data: dict):
        claim = data.get("claim") if isinstance(data.get("claim"), dict) else {}
        metadata = (
            data.get("metadata")
            if isinstance(data.get("metadata"), dict)
            else {}
        )

        claim_id = _clean_claim_id(
            data.get("claim_id")
            or claim.get("claim_id")
        )

        return (
            data.get("bulk_session_id")
            or claim.get("bulk_session_id")
            or metadata.get("bulk_session_id")
            or self._claim_bulk_sessions.get(claim_id)
        )

    def _compact_bulk_event(self, data: dict):
        claim = data.get("claim") if isinstance(data.get("claim"), dict) else {}

        return {
            "type": data.get("type") or data.get("event"),
            "event": data.get("event") or data.get("type"),
            "claim_id": data.get("claim_id") or claim.get("claim_id"),
            "status": data.get("status") or claim.get("status"),
            "stage": (
                data.get("stage")
                or data.get("current_stage")
                or claim.get("current_stage")
            ),
            "step": (
                data.get("step")
                or data.get("active_step")
                or claim.get("active_step")
            ),
            "progress": data.get("progress") or claim.get("progress"),
            "timestamp": data.get("timestamp") or datetime.utcnow().isoformat(),
        }

    async def _broadcast_now(self, data: dict):
        disconnected = []

        for connection in list(self.active_connections.values()):
            try:
                if connection.client_state != WebSocketState.CONNECTED:
                    disconnected.append(connection)
                    continue

                await connection.send_json(data)

            except Exception as exc:
                print(f"WS send error: {exc}", flush=True)
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)

    async def _flush_bulk_buffer(self, bulk_session_id: str):
        bulk_session_id = str(bulk_session_id)

        events = self._bulk_buffers.pop(bulk_session_id, [])
        self._bulk_flush_tasks.pop(bulk_session_id, None)

        if not events:
            return

        counts = {}

        for event in events:
            key = str(
                event.get("status")
                or event.get("event")
                or "UNKNOWN"
            ).upper()

            counts[key] = counts.get(key, 0) + 1

        await self._broadcast_now({
            "type": "bulk_events",
            "event": "bulk_events",
            "bulk_session_id": bulk_session_id,
            "count": len(events),
            "counts": counts,
            "events": events[-self._bulk_batch_size:],
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _schedule_bulk_flush(self, bulk_session_id: str):
        bulk_session_id = str(bulk_session_id)

        existing_task = self._bulk_flush_tasks.get(bulk_session_id)

        if existing_task and not existing_task.done():
            return

        async def delayed_flush():
            try:
                await asyncio.sleep(self._bulk_flush_interval_seconds)
                await self._flush_bulk_buffer(bulk_session_id)

            except asyncio.CancelledError:
                pass

            except Exception as exc:
                print(f"Bulk flush failed: {exc}", flush=True)
                self._bulk_flush_tasks.pop(bulk_session_id, None)

        self._bulk_flush_tasks[bulk_session_id] = asyncio.create_task(
            delayed_flush()
        )

    async def flush_bulk_session(self, bulk_session_id: str):
        if not bulk_session_id:
            return

        bulk_session_id = str(bulk_session_id)

        task = self._bulk_flush_tasks.pop(bulk_session_id, None)

        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        await self._flush_bulk_buffer(bulk_session_id)

    async def broadcast(self, data: dict, dedupe: bool = True):
        """
        Main websocket broadcast path.

        This owns:
        - outbound normalization
        - claim summary enrichment
        - dedupe
        - bulk batching
        - actual sending
        """

        data = self._normalize_outbound_event(data)

        if data is None:
            return

        if dedupe and not should_emit(data):
            return

        event_type = str(data.get("type") or data.get("event") or "")
        bulk_session_id = self._bulk_session_id(data)

        batchable = (
            bulk_session_id
            and event_type not in NON_BATCHABLE_BULK_EVENTS
        )

        if batchable:
            buffer = self._bulk_buffers.setdefault(str(bulk_session_id), [])
            buffer.append(self._compact_bulk_event(data))

            if len(buffer) >= self._bulk_batch_size:
                await self._flush_bulk_buffer(str(bulk_session_id))
            else:
                self._schedule_bulk_flush(str(bulk_session_id))

            return

        await self._broadcast_now(data)

    async def emit_once(self, event: dict):
        await self.broadcast(event, dedupe=True)
        return True

    @staticmethod
    def _count_items(value):
        if value in (None, "", [], {}):
            return 0

        if isinstance(value, dict):
            return len(value)

        if isinstance(value, (list, tuple, set)):
            return len(value)

        return 1

    @staticmethod
    def _duration_from_payload(start_time, end_time, explicit_duration):
        if explicit_duration not in (None, ""):
            try:
                return float(explicit_duration)
            except (TypeError, ValueError):
                return explicit_duration

        if not start_time or not end_time:
            return None

        try:
            start = datetime.fromisoformat(
                str(start_time).replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                str(end_time).replace("Z", "+00:00")
            )

            return max(0, (end - start).total_seconds() * 1000)

        except Exception:
            return None

    @staticmethod
    def _agent_label(value):
        return str(value or "Pipeline Agent").replace("_", " ").strip()

    @staticmethod
    def _normalize_agent_status(value):
        status = str(value or "INFO").strip().upper().replace("-", "_")

        if status in {
            "START",
            "STARTED",
            "INFO",
            "PROCESS",
            "PROCESSING",
            "IN_PROGRESS",
        }:
            return "RUNNING"

        if status in {
            "SUCCESS",
            "DONE",
            "COMPLETE",
            "COMPLETED",
            "ACCEPTED",
            "VALIDATED",
        }:
            return "COMPLETED"

        if status in {
            "ERROR",
            "FAILURE",
            "FAILED",
            "DENIED",
            "REJECTED",
            "HITL_REQUIRED",
        }:
            return "FAILED"

        if status in {
            "WARN",
            "WARNING",
            "WARNINGS",
            "PARTIAL",
            "COMPLETED_WITH_WARNINGS",
        }:
            return "WARNING"

        if status in {
            "PENDING",
            "QUEUED",
            "WAITING",
            "NEW",
            "CREATED",
        }:
            return "PENDING"

        return status

    def _build_agent_update(self, step, status=None, data=None):
        details = data or {}

        if not isinstance(details, dict):
            details = {"message": details}

        now = datetime.utcnow().isoformat()

        metrics = (
            details.get("metrics")
            if isinstance(details.get("metrics"), dict)
            else {}
        )

        input_payload = (
            details.get("input")
            or details.get("input_data")
            or details.get("claim")
            or details.get("request")
        )

        output_payload = (
            details.get("output")
            or details.get("output_data")
            or details.get("result")
            or details.get("response")
        )

        start_time = (
            details.get("start_time")
            or details.get("started_at")
            or details.get("startedAt")
            or details.get("timestamp")
            or now
        )

        end_time = (
            details.get("end_time")
            or details.get("completed_at")
            or details.get("completedAt")
        )

        duration = self._duration_from_payload(
            start_time,
            end_time,
            details.get("duration")
            or details.get("duration_seconds")
            or details.get("processing_time")
            or details.get("processingTime"),
        )

        normalized_status = self._normalize_agent_status(
            status or details.get("status")
        )

        stage = (
            details.get("stage")
            or details.get("current_stage")
            or details.get("active_step")
            or step
        )

        claim_id = self._extract_claim_id(details)

        if not claim_id:
            logger.error(
                "Missing claim_id for agent update",
                extra={
                    "step": step,
                    "status": normalized_status,
                    "details": details,
                },
            )
            return None

        best_claim_source = _extract_best_claim_source(details)

        base_event = emit_agent_event(
            claim_id,
            self._agent_label(
                details.get("agent")
                or details.get("current_agent")
                or step
            ),
            normalized_status,
            self._agent_label(stage),
            best_claim_source,
        )

        if base_event is None:
            return None

        warnings = (
            details.get("warnings")
            or details.get("warning")
            or details.get("errors")
            or []
        )

        if not isinstance(warnings, list):
            warnings = [warnings]

        persist_payload = {
            **base_event,
            "agent": self._agent_label(
                details.get("agent")
                or details.get("current_agent")
                or step
            ),
            "progress": details.get("progress"),
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "duration_seconds": duration,
            "started_at": start_time,
            "completed_at": end_time,
            "processing_time": duration,
            "confidence": (
                details.get("confidence")
                or details.get("ai_confidence")
            ),
            "reasoning": (
                details.get("reasoning")
                or details.get("reason")
                or details.get("message")
            ),
            "input": input_payload,
            "output": output_payload,
            "input_count": (
                details.get("input_count")
                or self._count_items(input_payload)
            ),
            "output_count": (
                details.get("output_count")
                or self._count_items(output_payload)
            ),
            "warnings": warnings,
            "metrics": {
                "cpu": metrics.get("cpu") or details.get("cpu"),
                "memory": metrics.get("memory") or details.get("memory"),
                "tokens": metrics.get("tokens") or details.get("tokens"),
                "latency": (
                    metrics.get("latency")
                    or details.get("latency")
                    or details.get("latency_ms")
                ),
                "throughput": (
                    metrics.get("throughput")
                    or details.get("throughput")
                ),
            },
            "details": details,
            "ai_summary": (
                details.get("ai_summary")
                or details.get("summary")
                or details.get("message")
            ),
            "next_agent": (
                details.get("next_agent")
                or details.get("handoff_to")
                or details.get("target_agent")
            ),
            "event_history": (
                details.get("event_history")
                or details.get("history")
            ),
            "timestamp": details.get("timestamp") or now,
            "step": step,
            "data": details,
        }

        persist_payload["agent_event"] = {
            "claim_id": claim_id,
            "agent": persist_payload["agent"],
            "stage": persist_payload["stage"],
            "status": (
                normalized_status.lower()
                if normalized_status in {
                    "RUNNING",
                    "COMPLETED",
                    "FAILED",
                    "WARNING",
                    "PENDING",
                }
                else "running"
            ),
            "started_at": persist_payload["started_at"],
            "completed_at": persist_payload["completed_at"],
            "processing_time": persist_payload["processing_time"],
            "confidence": persist_payload["confidence"],
            "reasoning": persist_payload["reasoning"],
            "input": persist_payload["input"],
            "output": persist_payload["output"],
            "warnings": persist_payload["warnings"],
            "metrics": persist_payload["metrics"],
            "ai_summary": persist_payload["ai_summary"],
            "next_agent": persist_payload["next_agent"],
            "event_history": persist_payload["event_history"],
            "progress": persist_payload.get("progress"),
        }

        claim_summary = _merge_claim_summary(
            self._claim_snapshots.get(claim_id, {}),
            _agent_claim_summary(best_claim_source),
        )

        if _claim_summary_has_data(claim_summary):
            self._claim_snapshots[claim_id] = claim_summary

        outbound_payload = {
            "type": "agent_update",
            "event": "agent_update",
            "claim_id": claim_id,
            "stage": details.get("stage") or stage,
            "status": normalized_status,
            "progress": details.get("progress"),
            "current_stage": details.get("current_stage") or stage,
            "current_agent": (
                details.get("current_agent")
                or details.get("agent")
                or step
            ),
            "active_step": (
                details.get("active_step")
                or details.get("current_step")
                or step
            ),
            "timestamp": details.get("timestamp") or now,
            "pipeline_state": details.get("pipeline_state"),
            "pipeline_status": details.get("pipeline_status"),
            "pipeline_result": details.get("pipeline_result"),
            "review_required": details.get("review_required"),
            "approval_required": details.get("approval_required"),
            "pipeline_paused": details.get("pipeline_paused"),
            "clearinghouse_status": details.get("clearinghouse_status"),
            "payment_status": details.get("payment_status"),
            "claim": claim_summary,
            "pipeline": _dict_or_empty(details.get("pipeline")),
            "metrics": _agent_metrics(details),
            "agent_detail": details.get("agent_detail"),
            "_persist_payload": persist_payload,
        }

        normalized_payload = _normalize_agent_update_payload(outbound_payload)
        normalized_payload["_persist_payload"] = persist_payload
        return normalized_payload

    async def send_agent_update(self, step, status=None, data=None):
        payload = self._build_agent_update(step, status, data)

        if payload is None:
            return

        persist_payload = payload.pop("_persist_payload", payload)

        try:
            from app.services.enterprise_observability_service import (
                persist_agent_event,
            )

            persist_agent_event(persist_payload)

        except Exception as exc:
            print(
                f"Agent event persistence skipped: {exc}",
                flush=True,
            )

        payload.pop("_persist_payload", None)
        payload.pop("details", None)
        payload.pop("data", None)
        payload.pop("input", None)
        payload.pop("output", None)
        payload.pop("agent_event", None)

        try:
            safe_log_payload = {
                "type": payload.get("type"),
                "event": payload.get("event"),
                "claim_id": payload.get("claim_id"),
                "stage": payload.get("stage"),
                "status": payload.get("status"),
                "progress": payload.get("progress"),
                "current_stage": payload.get("current_stage"),
                "current_agent": payload.get("current_agent"),
                "active_step": payload.get("active_step"),
                "pipeline_state": payload.get("pipeline_state"),
                "pipeline_status": payload.get("pipeline_status"),
                "review_required": payload.get("review_required"),
                "approval_required": payload.get("approval_required"),
                "pipeline_paused": payload.get("pipeline_paused"),
            }

            print(
                f"Sending agent update: {safe_log_payload}",
                flush=True,
            )
        except Exception as log_error:
            print(
                f"Sending agent update: log skipped: {log_error}",
                flush=True,
            )

        await self.broadcast(payload)

    async def send_event(self, step, status=None, data=None):
        """
        Compatibility method used by existing agents.

        Supports:
        await manager.send_event("validation", "completed", {...})
        await manager.send_event("validation", {"status": "completed", ...})
        """

        if isinstance(status, dict) and data is None:
            data = status
            status = data.get("status", "INFO")

        await self.send_agent_update(step, status, data or {})

    async def send_pipeline_update(self, claim_id: str, stage: str, pipeline: dict):
        payload = {
            "type": "pipeline_update",
            "event": "pipeline_update",
            "claim_id": claim_id,
            "stage": stage,
            "pipeline": pipeline,
            "timestamp": datetime.utcnow().isoformat(),
        }

        print(f"Pipeline update: {payload}", flush=True)

        await self.broadcast(payload)

    async def heartbeat(self, websocket: WebSocket):
        if websocket.client_state != WebSocketState.CONNECTED:
            return

        try:
            await websocket.send_json({
                "type": "heartbeat",
                "event": "heartbeat",
                "status": "CONNECTED",
                "timestamp": datetime.utcnow().isoformat(),
                "connections": len(self.active_connections),
            })

        except Exception as exc:
            print(f"WS heartbeat failed: {exc}", flush=True)
            self.disconnect(websocket)


manager = ConnectionManager()

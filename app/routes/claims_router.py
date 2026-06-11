import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from app.case_management.models.case_models import Case, CaseAssignment, CaseAuditLog, CaseComment, CaseEscalation
from app.case_management.schemas import CaseCreate
from app.case_management.services.case_service import CaseService
from app.db.database import get_db
from app.agents.ai_suggestions.auto_correct_agent import AutoCorrectAgent
from app.agents.ai_suggestions.claim_repair_engine import ClaimRepairEngine
from app.agents.ai_suggestions.suggestion_agent import AISuggestionAgent
from app.agents.denial_ai.llm_denial_agent import LLMDenialAgent
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.validation.validation_agent import ValidationAgent
from app.models.claim_model import Claim, ValidationLog
from app.models.ai_repair_model import AISuggestion, AppealHistory, CorrectionHistory, ExtractionConfidence, RepairLog, TextractEntity
from app.models.clearinghouse_model import ClearinghouseEvent, DenialHistory, PaymentHistory, SubmissionHistory
from app.models.compliance_audit_model import ComplianceAudit
from app.models.feedback_model import Feedback
from app.models.learning_metrics_model import LearningMetrics
from app.models.pipeline_events_model import PipelineEvent
from app.models.claim_history_model import ClaimHistory
from app.models.enterprise_observability_model import AgentEventRecord, ClaimMetric, DecisionLog
from app.services.edi_service import build_837I, build_837P
from app.services.clearinghouse_orchestration_service import ClearinghouseOrchestrationService
from app.services.audit_service import log_audit
from app.services.cms1500_service import Cms1500TemplateUnavailable, generate_cms1500_pdf_bytes, store_cms1500_pdf
from app.services.enterprise_observability_service import (
    audit_evidence_for_claim,
    build_extraction_summary,
    extract_ocr_text,
    hitl_reasons_for_claim,
    route_case_for_claim,
    validate_claim_enterprise,
)
from app.websocket.manager import manager

router = APIRouter()

EXPORT_ROOT = Path("exports").resolve()
FINAL_CLAIM_STATUSES = {"APPROVED", "PAID", "REJECTED", "CLOSED", "COMPLETED", "FINALIZED"}
PIPELINE_STAGE_IDS = ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE", "DENIAL_AI", "PAYMENT", "LEARNING", "ANALYTICS"]
CLEARINGHOUSE_WAITING_STATUSES = {
    "WAITING_FOR_APPROVAL",
    "PENDING_CLEARINGHOUSE",
    "PENDING_APPROVAL",
}
PIPELINE_STEP_STAGE_MAP = {
    "uploaded": "OCR",
    "intake": "OCR",
    "extract": "OCR",
    "extraction": "OCR",
    "ocr": "OCR",
    "ocr_done": "OCR",
    "rules_validated": "VALIDATION",
    "validated": "VALIDATION",
    "validation": "VALIDATION",
    "eligibility_checked": "VALIDATION",
    "compliance": "COMPLIANCE",
    "compliance_checked": "COMPLIANCE",
    "case_orchestrated": "COMPLIANCE",
    "submitted": "SUBMISSION",
    "submission": "SUBMISSION",
    "edi_generation": "SUBMISSION",
    "claim_form": "SUBMISSION",
    "clearinghouse_queued": "CLEARINGHOUSE",
    "clearinghouse_accepted": "CLEARINGHOUSE",
    "acknowledged": "CLEARINGHOUSE",
    "auto_accepted": "CLEARINGHOUSE",
    "denial_checked": "DENIAL_AI",
    "denial_ai": "DENIAL_AI",
    "denial_ai_analyzed": "DENIAL_AI",
    "paid": "PAYMENT",
    "payment": "PAYMENT",
    "learning": "LEARNING",
    "learning_updated": "LEARNING",
    "analytics": "ANALYTICS",
    "analytics_done": "ANALYTICS",
}


def make_json_safe(value, seen=None):
    """
    Converts objects to JSON-safe values and removes circular references.
    Safe for PostgreSQL JSON/JSONB columns.
    """
    if seen is None:
        seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    obj_id = id(value)
    if obj_id in seen:
        return None

    if isinstance(value, dict):
        seen.add(obj_id)
        cleaned = {}

        for key, item in value.items():
            if key in {"payload", "_sa_instance_state"}:
                continue

            cleaned[str(key)] = make_json_safe(item, seen)

        seen.remove(obj_id)
        return cleaned

    if isinstance(value, (list, tuple, set)):
        seen.add(obj_id)
        cleaned = [make_json_safe(item, seen) for item in value]
        seen.remove(obj_id)
        return cleaned

    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _serialize_claim(claim: Claim) -> Dict[str, Any]:
    payload = claim.payload or {}
    claim_payload = payload.get("claim", payload)
    return {
        "claim_id": claim.claim_id,
        "status": claim.status,
        "stage": claim.stage,
        "total_charge": claim.total_charge,
        "payload": payload,
        "claim": claim_payload,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "uploaded_at": payload.get("uploaded_at") or claim_payload.get("uploaded_at") or (claim.created_at.isoformat() if claim.created_at else None),
        "last_activity_at": payload.get("last_activity_at") or claim_payload.get("last_activity_at") or (claim.updated_at.isoformat() if claim.updated_at else None),
        "is_new_upload": payload.get("is_new_upload", claim_payload.get("is_new_upload", False)),
        "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
        "artifact_paths": _artifact_paths_from_payload(payload),
        "compliance_results": payload.get("compliance") or payload.get("compliance_results") or {},
        "learning_metrics": payload.get("learning") or payload.get("learning_metrics") or {},
        "analytics_summary": payload.get("analytics") or payload.get("analytics_summary") or {},
        "clearinghouse_ack": payload.get("ack") or payload.get("clearinghouse_ack") or {},
        "extraction": payload.get("extraction") or payload.get("claim", {}).get("extraction") or {},
        "field_confidence": payload.get("field_confidence") or payload.get("claim", {}).get("field_confidence") or [],
        "form_detection": payload.get("form_detection") or payload.get("claim", {}).get("form_detection") or {},
        "services": payload.get("services") or payload.get("claim", {}).get("services") or [],
    }


def _serialize_event(event: PipelineEvent) -> Dict[str, Any]:
    return {
        "id": event.id,
        "claim_id": event.claim_id,
        "agent": event.agent,
        "status": event.status,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "message": event.message,
        "execution_time": event.execution_time,
    }


def _normalize_pipeline_status(value: Any) -> str:
    status = str(value or "PENDING").strip().upper()
    if status in {"SUCCESS", "DONE", "COMPLETE"}:
        return "COMPLETED"
    if status in {"START", "STARTED", "PROCESS", "PROCESSING", "ACTIVE", "IN_PROGRESS", "RUNNING"}:
        return "RUNNING"
    if status in {"ERROR", "FAILURE"}:
        return "FAILED"
    if status in {"PAID", "APPROVED", "FINALIZED", "CLOSED"}:
        return "COMPLETED"
    return status


def _pipeline_stage_id(value: Any) -> Optional[str]:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if token in PIPELINE_STAGE_IDS:
        return token
    if token in {"DENIAL", "DENIALAI"}:
        return "DENIAL_AI"
    if token in {"ACK", "ACKNOWLEDGMENT", "PAYER"}:
        return "CLEARINGHOUSE"
    if token in {"EDI", "CLAIM_FORM", "SUBMIT"}:
        return "SUBMISSION"
    return PIPELINE_STEP_STAGE_MAP.get(token.lower())


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} sec"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {remaining} sec" if remaining else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"


def _duration_between(started_at: Any, completed_at: Any) -> str:
    start = _parse_dt(started_at)
    end = _parse_dt(completed_at)
    if not start or not end:
        return ""
    return _format_duration((end - start).total_seconds())


def _format_processing_duration(value: Any) -> str:
    if value is None:
        return ""
    try:
        return _format_duration(float(value))
    except (TypeError, ValueError):
        return str(value)


def _build_pipeline_summary(claim: Claim, events: List[PipelineEvent]) -> Dict[str, Any]:
    payload = claim.payload or {}
    claim_payload = payload.get("claim", payload)
    pipeline = payload.get("pipeline") or {}
    steps = pipeline.get("steps") if isinstance(pipeline.get("steps"), dict) else {}
    stage_history = claim_payload.get("stage_history") or payload.get("stage_history") or []
    completed_stages = (
        pipeline.get("completed_stages")
        or payload.get("completed_stages")
        or claim_payload.get("completed_stages")
        or []
    )
    stage_status = (
        pipeline.get("stage_status")
        or payload.get("stage_status")
        or claim_payload.get("stage_status")
        or {}
    )
    overall_status = _normalize_pipeline_status(
        payload.get("overall_status")
        or claim_payload.get("overall_status")
        or payload.get("pipeline_status")
        or pipeline.get("pipeline_status")
        or claim_payload.get("pipeline_status")
        or claim.status
        or pipeline.get("pipeline_state")
    )
    terminal_statuses = {"COMPLETED", "PAID", "APPROVED", "FINALIZED", "CLOSED", "COMMAND_CENTER"}
    has_terminal_claim_status = any(
        _normalize_pipeline_status(value) in terminal_statuses
        for value in (
            claim.status,
            payload.get("status"),
            claim_payload.get("status"),
            payload.get("overall_status"),
            claim_payload.get("overall_status"),
        )
    )
    is_completed = (
        overall_status in terminal_statuses
        or has_terminal_claim_status
        or payload.get("pipeline_completed") is True
        or claim_payload.get("pipeline_completed") is True
        or pipeline.get("pipeline_state") == "COMPLETED"
        or pipeline.get("active_step") == "completed"
    )
    if is_completed:
        overall_status = "COMPLETED"

    stage_map: Dict[str, Dict[str, Any]] = {
        stage_id: {
            "id": stage_id,
            "status": "PENDING",
            "started_at": "",
            "completed_at": "",
            "duration": "",
        }
        for stage_id in PIPELINE_STAGE_IDS
    }

    for entry in stage_history:
        stage_id = _pipeline_stage_id(entry.get("stage") or entry.get("id") or entry.get("agent"))
        if not stage_id:
            continue
        stage = stage_map[stage_id]
        raw_status = str(entry.get("status") or entry.get("state") or "").strip().upper()
        status = _normalize_pipeline_status(entry.get("status") or entry.get("state"))
        if raw_status.endswith("_COMPLETED"):
            status = "COMPLETED"
        elif raw_status.endswith("_STARTED"):
            status = "RUNNING"
        if status in {
            "COMPLETED",
            "RUNNING",
            "FAILED",
            "REJECTED",
            "DENIED",
            "HITL_REQUIRED",
            "MANUAL_REVIEW_REQUIRED",
            "WAITING_FOR_REVIEW",
        }:
            stage["status"] = status
        stage["started_at"] = entry.get("started_at") or stage["started_at"]
        stage["completed_at"] = entry.get("completed_at") or stage["completed_at"]
        if entry.get("duration_seconds") is not None:
            try:
                stage["duration"] = _format_duration(float(entry.get("duration_seconds") or 0))
            except (TypeError, ValueError):
                pass
        elif stage["started_at"] and stage["completed_at"]:
            stage["duration"] = _duration_between(stage["started_at"], stage["completed_at"])

    for step, done in steps.items():
        if not done:
            continue
        stage_id = _pipeline_stage_id(step)
        if stage_id:
            stage_map[stage_id]["status"] = "COMPLETED"

    for completed_stage in completed_stages:
        stage_id = _pipeline_stage_id(completed_stage)
        if stage_id:
            stage_map[stage_id]["status"] = "COMPLETED"

    for event in events:
        stage_id = _pipeline_stage_id(event.agent)
        if not stage_id:
            continue
        status = _normalize_pipeline_status(event.status)
        stage = stage_map[stage_id]
        if status == "RUNNING":
            stage["status"] = "RUNNING"
            stage["started_at"] = stage["started_at"] or (event.timestamp.isoformat() if event.timestamp else "")
        elif status == "COMPLETED":
            stage["status"] = "COMPLETED"
            stage["completed_at"] = stage["completed_at"] or (event.timestamp.isoformat() if event.timestamp else "")
            stage["started_at"] = stage["started_at"] or stage["completed_at"]
        elif status in {"FAILED", "REJECTED", "DENIED", "HITL_REQUIRED", "MANUAL_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"}:
            stage["status"] = status
            stage["started_at"] = stage["started_at"] or (event.timestamp.isoformat() if event.timestamp else "")

    if isinstance(stage_status, dict):
        for raw_stage, raw_status in stage_status.items():
            stage_id = _pipeline_stage_id(raw_stage)
            if stage_id:
                stage_map[stage_id]["status"] = _normalize_pipeline_status(raw_status)

    active_stage_id = _pipeline_stage_id(
        pipeline.get("current_agent")
        or pipeline.get("current_stage")
        or pipeline.get("active_step")
        or claim_payload.get("current_agent")
        or claim_payload.get("current_stage")
        or claim.stage
    )
    if active_stage_id and not is_completed and stage_map[active_stage_id]["status"] == "PENDING":
        stage_map[active_stage_id]["status"] = "RUNNING"
    if not is_completed and overall_status == "RUNNING" and not any(
        stage["status"] == "RUNNING" for stage in stage_map.values()
    ):
        next_stage_id = next(
            (stage_id for stage_id in PIPELINE_STAGE_IDS if stage_map[stage_id]["status"] == "PENDING"),
            None,
        )
        if next_stage_id:
            stage_map[next_stage_id]["status"] = "RUNNING"

    stages = [stage_map[stage_id] for stage_id in PIPELINE_STAGE_IDS]
    if not is_completed and all(stage["status"] == "COMPLETED" for stage in stages):
        is_completed = True
        overall_status = "COMPLETED"
    if is_completed:
        for stage in stages:
            stage["status"] = "COMPLETED"
        current_agent = None
        progress = 100
        workflow_state = "Finished"
    else:
        running_stage = next((stage for stage in stages if stage["status"] == "RUNNING"), None)
        current_agent = running_stage["id"] if running_stage else None
        completed_count = sum(1 for stage in stages if stage["status"] == "COMPLETED")
        progress = int(round((completed_count / len(stages)) * 100))
        if running_stage:
            progress = min(99, max(progress, int(round(((completed_count + 0.5) / len(stages)) * 100))))
        workflow_state = "In Progress" if running_stage else "Pending"

    started_at = (
        pipeline.get("started_at")
        or payload.get("started_at")
        or claim_payload.get("started_at")
        or (claim.created_at.isoformat() if claim.created_at else None)
    )
    completed_at = (
        pipeline.get("completed_at")
        or payload.get("completed_at")
        or claim_payload.get("completed_at")
        or payload.get("finalized_at")
        or claim_payload.get("finalized_at")
        or (claim.updated_at.isoformat() if is_completed and claim.updated_at else None)
    )
    duration = (
        pipeline.get("duration")
        or payload.get("duration")
        or claim_payload.get("duration")
        or _duration_between(started_at, completed_at)
        or _format_processing_duration(claim_payload.get("processing_duration") or payload.get("processing_duration"))
    )

    return {
        "claim_id": claim.claim_id,
        "overall_status": overall_status,
        "current_agent": current_agent,
        "workflow_state": workflow_state,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration": duration or ("Pending" if not is_completed else ""),
        "progress": progress,
        "stages": stages,
        "stage_status": stage_status if isinstance(stage_status, dict) else {},
    }


def _payment_amount(payload: Dict[str, Any], claim_payload: Dict[str, Any]) -> float:
    payment = payload.get("payment") or claim_payload.get("payment") or {}
    try:
        return float(
            payment.get("paid_amount")
            or payment.get("amount")
            or payment.get("total_paid")
            or claim_payload.get("paid_amount")
            or claim_payload.get("total_charge")
            or payload.get("total_charge")
            or 0
        )
    except (TypeError, ValueError):
        return 0


def _duration_seconds(payload: Dict[str, Any], claim_payload: Dict[str, Any]) -> float:
    history = claim_payload.get("stage_history") or payload.get("stage_history") or []
    total = 0.0
    for entry in history:
        try:
            total += float(entry.get("duration_seconds") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 3)


def _serialize_command_claim(claim: Claim, include_detail: bool = False) -> Dict[str, Any]:
    payload = claim.payload or {}
    claim_payload = payload.get("claim", payload)
    pipeline = payload.get("pipeline") or {}
    validation = payload.get("validation") or {}
    denial = payload.get("denial") or payload.get("denial_ai") or claim_payload.get("denial_ai") or {}
    payment = payload.get("payment") or claim_payload.get("payment") or {}
    clearinghouse = payload.get("clearinghouse") or claim_payload.get("clearinghouse") or {}
    artifacts = _artifact_paths_from_payload(payload) or {}
    finalized_at = claim_payload.get("finalized_at") or payload.get("finalized_at") or (claim.updated_at.isoformat() if claim.updated_at else None)
    payment_amount = _payment_amount(payload, claim_payload)
    duration = claim_payload.get("processing_duration") or payload.get("processing_duration") or _duration_seconds(payload, claim_payload)

    data: Dict[str, Any] = {
        "claim_id": claim.claim_id,
        "patient": claim_payload.get("patient") or {},
        "provider": claim_payload.get("provider") or {},
        "payer": claim_payload.get("payer") or payload.get("payer") or {},
        "date_of_service": claim_payload.get("date_of_service") or claim_payload.get("dos"),
        "status": claim.status,
        "workspace": claim_payload.get("workspace") or payload.get("workspace") or "COMMAND_CENTER",
        "payment_amount": payment_amount,
        "payment_status": payment.get("status") or claim_payload.get("payment_status") or ("PAID" if payment_amount else "PENDING"),
        "denial_status": denial.get("status") or denial.get("denial_prediction") or ("DENIED" if claim.status == "REJECTED" else "CLEARED"),
        "completed_at": finalized_at,
        "processing_duration": duration,
        "total_charge": claim_payload.get("total_charge") or claim.total_charge or 0,
        "cms1500_pdf_url": f"/api/claims/{claim.claim_id}/cms1500",
        "ub04_pdf_url": f"/api/claims/{claim.claim_id}/ub04",
        "edi_url": f"/api/claims/{claim.claim_id}/edi",
        "artifact_paths": artifacts,
    }
    if include_detail:
        data.update({
            "claim": claim_payload,
            "pipeline": pipeline,
            "validation": validation,
            "clearinghouse": clearinghouse,
            "denial": denial,
            "payment": payment,
            "edi": {
                "url": data["edi_url"],
                "payload": payload.get("edi") or payload.get("edi_payload") or claim_payload.get("edi") or clearinghouse.get("response") or {},
                "ack": payload.get("ack") or claim_payload.get("ack") or {},
                "submission": claim_payload.get("submission") or payload.get("submission") or {},
                "payer_response": claim_payload.get("payer_response") or payload.get("payer_response") or {},
            },
            "audit_history": claim_payload.get("stage_history") or payload.get("stage_history") or [],
            "analytics": payload.get("analytics") or claim_payload.get("analytics") or {
                "automation_score": 96 if not payload.get("case") else 72,
                "denial_probability": denial.get("risk_score") or denial.get("denial_risk") or 0,
                "ai_confidence": claim_payload.get("ai_confidence") or validation.get("ai_confidence") or claim_payload.get("confidence") or 0,
                "validation_score": claim_payload.get("validation_score") or validation.get("validation_score") or validation.get("score") or 0,
            },
            "documents": [
                {"label": "CMS1500 PDF", "type": "pdf", "url": data["cms1500_pdf_url"]},
                {"label": "UB04 PDF", "type": "pdf", "url": data["ub04_pdf_url"]},
                {"label": "EDI Payload", "type": "edi", "url": data["edi_url"]},
            ],
        })
    return data


def _artifact_paths_from_payload(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    artifacts = payload.get("generated_artifacts") or payload.get("artifacts") or {}
    form = artifacts.get("form") or artifacts.get("pdf") or {}
    edi = artifacts.get("edi") or {}
    return {
        "cms1500": form.get("local_path") or form.get("path") or payload.get("cms1500_path"),
        "ub04": artifacts.get("ub04_path") or form.get("ub04_path") or payload.get("ub04_path"),
        "edi": edi.get("local_path") or edi.get("path") or payload.get("edi_path"),
    }


def _get_claim_or_404(claim_id: str, db: Session) -> Claim:
    claim = db.query(Claim).filter(Claim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def _safe_claim_payload(claim: Claim) -> Dict[str, Any]:
    payload = claim.payload or {}
    return payload.get("claim", payload)


def get_risk_score(claim_payload: Dict[str, Any]) -> float:
    risk = claim_payload.get("risk_score")
    if risk is None:
        risk = (claim_payload.get("denial_risk") or {}).get("risk_score")
    try:
        value = float(risk or 0)
    except (TypeError, ValueError):
        return 0
    return value * 100 if 0 < value <= 1 else value


def _set_path(data: Dict[str, Any], path: str, value: Any):
    cursor = data
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _existing_path(path_value: Optional[str]) -> Optional[Path]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path if path.exists() and path.is_file() else None


def _delete_artifacts_for_claim(claim_id: str, payload: Dict[str, Any]) -> List[str]:
    deleted: List[str] = []
    candidates = list(_artifact_paths_from_payload(payload).values())
    export_dir = EXPORT_ROOT / claim_id
    if export_dir.exists() and export_dir.is_dir():
        candidates.extend(str(path) for path in export_dir.rglob("*") if path.is_file())
    candidates.extend(str(path) for path in EXPORT_ROOT.glob(f"{claim_id}*") if path.is_file())

    for candidate in candidates:
        path = _existing_path(candidate)
        if not path:
            continue
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(EXPORT_ROOT)):
                continue
            resolved.unlink(missing_ok=True)
            deleted.append(str(resolved))
        except OSError:
            continue
    try:
        if export_dir.exists() and export_dir.is_dir():
            for child in sorted(export_dir.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            export_dir.rmdir()
    except OSError:
        pass
    return deleted


def _delete_claim_rows(db: Session, claim_id: str):
    case_ids = [row[0] for row in db.query(Case.case_id).filter(Case.claim_id == claim_id).all()]
    if case_ids:
        db.query(CaseAssignment).filter(CaseAssignment.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(CaseAuditLog).filter(CaseAuditLog.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(CaseComment).filter(CaseComment.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(CaseEscalation).filter(CaseEscalation.case_id.in_(case_ids)).delete(synchronize_session=False)
    for model in [
        AISuggestion,
        AppealHistory,
        CorrectionHistory,
        RepairLog,
        ExtractionConfidence,
        TextractEntity,
        ClearinghouseEvent,
        DenialHistory,
        PaymentHistory,
        SubmissionHistory,
        ComplianceAudit,
        Feedback,
        LearningMetrics,
        PipelineEvent,
        ValidationLog,
        AgentEventRecord,
        ClaimMetric,
        DecisionLog,
    ]:
        db.query(model).filter(model.claim_id == claim_id).delete(synchronize_session=False)
    db.query(ClaimHistory).filter(ClaimHistory.claim_id == claim_id).delete(synchronize_session=False)
    db.execute(text("DELETE FROM services WHERE claim_id = :claim_id"), {"claim_id": claim_id})
    db.query(Case).filter(Case.claim_id == claim_id).delete(synchronize_session=False)
    db.query(Claim).filter(Claim.claim_id == claim_id).delete(synchronize_session=False)


def _write_minimal_pdf(path: Path, title: str, lines: List[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\\n".join([title, *lines]).replace("(", "[").replace(")", "]")
    stream = f"BT /F1 12 Tf 50 760 Td ({text}) Tj ET"
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        f"5 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
        "xref\n0 6\n0000000000 65535 f \n"
        "trailer << /Root 1 0 R /Size 6 >>\nstartxref\n0\n%%EOF\n"
    )
    path.write_bytes(pdf.encode("latin-1", errors="ignore"))
    return path


def _write_cms1500_template_pdf(path: Path, claim: Claim) -> Path:
    claim_payload = _safe_claim_payload(claim)
    claim_data = {
        **claim_payload,
        "claim_id": claim.claim_id,
        "total_charge": claim_payload.get("total_charge") or claim.total_charge or 0,
    }
    try:
        pdf_bytes, _ = generate_cms1500_pdf_bytes(claim_data)
        store_cms1500_pdf(pdf_bytes, claim.claim_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        return path
    except Cms1500TemplateUnavailable:
        return _write_minimal_pdf(
            path,
            "CMS1500 Template Unavailable",
            [
                f"Claim ID: {claim.claim_id}",
                "Route: MANUAL_REVIEW",
                "Reason: CMS template unavailable",
                f"Generated: {datetime.utcnow().isoformat()}",
            ],
        )


def _artifact_file(claim: Claim, artifact_type: str) -> Path:
    payload = claim.payload or {}
    existing = _existing_path(_artifact_paths_from_payload(payload).get(artifact_type))
    if existing:
        return existing

    claim_payload = _safe_claim_payload(claim)
    claim_dir = EXPORT_ROOT / claim.claim_id

    if artifact_type == "edi":
        claim_dir.mkdir(parents=True, exist_ok=True)
        edi_path = claim_dir / f"{claim.claim_id}.edi"
        if not edi_path.exists():
            builder = build_837I if str(claim_payload.get("encounter_type", "")).lower() in {"inpatient", "ub04", "institutional"} else build_837P
            edi_path.write_text(builder({**claim_payload, "claim_id": claim.claim_id}), encoding="utf-8")
        return edi_path

    if artifact_type == "ub04":
        return _write_minimal_pdf(
            claim_dir / f"{claim.claim_id}-UB04.pdf",
            "UB04 Claim Artifact",
            [f"Claim ID: {claim.claim_id}", f"Status: {claim.status or 'PENDING'}", f"Generated: {datetime.utcnow().isoformat()}"],
        )

    return _write_cms1500_template_pdf(
        claim_dir / f"{claim.claim_id}-CMS1500.pdf",
        claim,
    )


@router.get("/claims", response_model=List[dict])
async def get_claims(db: Session = Depends(get_db)):
    claims = db.query(Claim).order_by(Claim.updated_at.desc()).all()
    return [_serialize_claim(claim) for claim in claims]


@router.get("/claims/{claim_id}", response_model=dict)
async def get_claim(claim_id: str, db: Session = Depends(get_db)):
    return _serialize_claim(_get_claim_or_404(claim_id, db))


@router.delete("/claims/{claim_id}", response_model=dict)
@router.delete("/api/claims/{claim_id}", response_model=dict, include_in_schema=False)
async def delete_claim(claim_id: str, request: Request, db: Session = Depends(get_db)):
    role = (request.headers.get("x-user-role") or request.query_params.get("role") or "Admin").strip().lower()
    deleted_by = request.headers.get("x-user-email") or request.query_params.get("deleted_by") or "SYSTEM"
    if role not in {"admin", "supervisor"}:
        raise HTTPException(status_code=403, detail="Only Admin or Supervisor can delete claims")

    claim = db.query(Claim).filter(Claim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    payload = claim.payload or {}
    log_audit(claim_id, "DELETE_CLAIM", "requested", {
        "deleted_by": deleted_by,
        "timestamp": datetime.utcnow().isoformat(),
    })

    try:
        deleted_files = _delete_artifacts_for_claim(claim_id, payload)
        _delete_claim_rows(db, claim_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Claim delete failed: {exc}") from exc

    try:
        await manager.broadcast({
            "type": "claim_deleted",
            "event": "claim_deleted",
            "claim_id": claim_id,
            "status": "DELETED",
            "deleted_by": deleted_by,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception:
        pass

    return {
        "success": True,
        "claim_id": claim_id,
        "message": "Claim deleted successfully",
        "deleted_files": deleted_files,
    }


@router.get("/claims/{claim_id}/pipeline", response_model=dict)
async def get_claim_pipeline(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    events = (
        db.query(PipelineEvent)
        .filter(PipelineEvent.claim_id == claim_id)
        .order_by(PipelineEvent.timestamp.asc())
        .all()
    )
    validation = (
        db.query(ValidationLog)
        .filter(ValidationLog.claim_id == claim_id)
        .order_by(ValidationLog.created_at.desc())
        .first()
    )
    payload = claim.payload or {}
    pipeline_summary = _build_pipeline_summary(claim, events)
    return {
        **_serialize_claim(claim),
        **pipeline_summary,
        "pipeline": payload.get("pipeline") or {"stage": claim.stage, "events": [_serialize_event(event) for event in events]},
        "events": [_serialize_event(event) for event in events],
        "validation": {
            "status": validation.status if validation else payload.get("validation", {}).get("status"),
            "errors": validation.errors if validation else payload.get("validation", {}).get("errors", []),
        },
    }


@router.get("/claims/{claim_id}/extraction-summary", response_model=dict)
async def get_extraction_summary(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    return build_extraction_summary(claim, db)


@router.get("/claims/{claim_id}/ocr-preview", response_model=dict)
async def get_ocr_preview(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    return {
        "claim_id": claim_id,
        "text": extract_ocr_text(claim, db),
    }


@router.get("/claims/{claim_id}/validation-summary", response_model=dict)
async def get_validation_summary(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    payload = claim.payload or {}
    validation = payload.get("validation") or _safe_claim_payload(claim).get("validation") or {}
    validation_result = validation.get("validation_result") if isinstance(validation, dict) else None
    if not validation_result:
        validation_result = validate_claim_enterprise(claim, db)
    return {
        "claim_id": claim_id,
        "validation_result": validation_result,
        "hitl_reason": hitl_reasons_for_claim(claim, validation_result=validation_result, db=db),
    }


@router.get("/claims/{claim_id}/case-orchestration", response_model=dict)
async def get_case_orchestration(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    service = CaseService(db)
    existing = service.get_case_by_claim(claim_id)
    validation = validate_claim_enterprise(claim, db)
    route = route_case_for_claim(claim, validation)
    if existing:
        serialized = service.serialize_case(existing, include_children=True)
        return {
            "claim_id": claim_id,
            "case": serialized,
            "routing": route,
            "case_id": serialized.get("case_id"),
            "current_owner": serialized.get("current_owner"),
            "priority": serialized.get("priority"),
            "next_stage": serialized.get("next_stage") or route.get("next_stage"),
            "sla_deadline": serialized.get("sla_deadline") or serialized.get("sla_due_at"),
            "escalation_level": serialized.get("escalation_level", 0),
        }
    return {
        "claim_id": claim_id,
        "case": None,
        "routing": route,
        "case_id": None,
        "current_owner": route.get("assigned_team"),
        "priority": route.get("priority"),
        "next_stage": route.get("next_stage"),
        "sla_deadline": route.get("sla_deadline"),
        "escalation_level": route.get("escalation_level", 0),
    }


@router.get("/claims/{claim_id}/agent-events", response_model=dict)
async def get_agent_events(claim_id: str, limit: int = 200, db: Session = Depends(get_db)):
    _get_claim_or_404(claim_id, db)
    rows = (
        db.query(AgentEventRecord)
        .filter(AgentEventRecord.claim_id == claim_id)
        .order_by(AgentEventRecord.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "claim_id": claim_id,
        "events": [
            {
                "id": row.id,
                "agent": row.agent,
                "stage": row.stage,
                "status": row.status,
                "progress": row.progress,
                "duration": row.duration,
                "input_count": row.input_count,
                "output_count": row.output_count,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.get("/claims/{claim_id}/audit-evidence", response_model=dict)
async def get_claim_audit_evidence(claim_id: str, db: Session = Depends(get_db)):
    _get_claim_or_404(claim_id, db)
    return audit_evidence_for_claim(claim_id, db)


@router.get("/claims/{claim_id}/suggestions", response_model=dict)
async def get_claim_suggestions(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    stored = db.query(AISuggestion).filter(AISuggestion.claim_id == claim_id).order_by(AISuggestion.created_at.desc()).all()
    if stored:
        return {
            "claim_id": claim_id,
            "suggestions": [
                {
                    "id": item.id,
                    "field": item.field,
                    "current": item.current_value,
                    "suggested": item.suggested_value,
                    "confidence": item.confidence,
                    "reason": item.reason,
                    "status": item.status,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in stored
            ],
        }

    state = await AISuggestionAgent().run({
        "claim": _safe_claim_payload(claim),
        "validation": (claim.payload or {}).get("validation", {}),
    })
    suggestions = state.get("ai_suggestions", [])
    ClaimRepairEngine(db)._store_suggestions(claim_id, suggestions)
    return {"claim_id": claim_id, "suggestions": suggestions}


@router.post("/claims/{claim_id}/apply-correction", response_model=dict)
async def apply_claim_correction(claim_id: str, payload: dict, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    claim_payload = _safe_claim_payload(claim_row)
    suggestions = payload.get("suggestions") or []
    action = str(payload.get("action", "accepted")).upper()

    if payload.get("field"):
        suggestions.append({
            "field": payload.get("field"),
            "current": payload.get("current"),
            "suggested": payload.get("suggested"),
            "confidence": payload.get("confidence", 1.0),
            "reason": payload.get("reason", "Manual correction"),
        })

    if action == "REJECTED":
        for suggestion in suggestions:
            db.add(CorrectionHistory(
                claim_id=claim_id,
                field=suggestion.get("field"),
                previous_value=suggestion.get("current"),
                corrected_value=suggestion.get("suggested"),
                source="USER_REJECTED",
                accepted="REJECTED",
                confidence=float(suggestion.get("confidence") or 0),
            ))
        db.add(LearningMetrics(
            claim_id=claim_id,
            denial_patterns=[],
            correction_history={"rejected_suggestions": suggestions},
            confidence_trends={"correction_accuracy": 0},
            improvement_signals={"repair_success_rate": 0},
        ))
        db.commit()
        return {"claim_id": claim_id, "status": "REJECTED", "claim": claim_payload}

    state = await AutoCorrectAgent().run({"claim": claim_payload, "ai_suggestions": suggestions})
    corrected_claim = state.get("claim", claim_payload)
    for correction in state.get("correction_history", []):
        db.add(CorrectionHistory(
            claim_id=claim_id,
            field=correction.get("field"),
            previous_value=correction.get("previous"),
            corrected_value=correction.get("corrected"),
            source="USER_ACCEPTED",
            accepted="ACCEPTED",
            confidence=float(correction.get("confidence") or 0),
        ))

    original_payload = claim_row.payload or {}
    original_payload["claim"] = corrected_claim
    original_payload["correction_history"] = [
        *original_payload.get("correction_history", []),
        *state.get("correction_history", []),
    ]
    claim_row.payload = original_payload
    flag_modified(claim_row, "payload")
    if corrected_claim.get("requires_hitl"):
        claim_row.status = "WAITING_FOR_REVIEW"
        claim_row.stage = "WAITING_FOR_REVIEW"

    db.add(LearningMetrics(
        claim_id=claim_id,
        denial_patterns=[],
        correction_history={"accepted_suggestions": suggestions},
        confidence_trends={"correction_accuracy": 1},
        improvement_signals={"repair_success_rate": 1},
    ))
    db.commit()
    status = "WAITING_FOR_REVIEW" if corrected_claim.get("requires_hitl") else "APPLIED"
    return {"claim_id": claim_id, "status": status, "claim": corrected_claim, "corrections": state.get("correction_history", [])}


@router.post("/claims/{claim_id}/retry-validation", response_model=dict)
async def retry_claim_validation(claim_id: str, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    state = await ValidationAgent().run({"claim": _safe_claim_payload(claim_row)})
    payload = claim_row.payload or {}
    payload["claim"] = state.get("claim", _safe_claim_payload(claim_row))
    payload["validation"] = state.get("validation", {})
    claim_row.payload = payload
    flag_modified(claim_row, "payload")
    claim_row.status = "VALIDATED" if state.get("validation", {}).get("valid") else "HITL_REQUIRED"
    db.add(RepairLog(
        claim_id=claim_id,
        status="VALIDATION_RETRY_SUCCESS" if state.get("validation", {}).get("valid") else "VALIDATION_RETRY_FAILED",
        retry_count=1,
        confidence_score=float(state.get("validation", {}).get("score") or 0),
        details=state.get("validation", {}),
    ))
    db.commit()
    return {"claim_id": claim_id, "status": claim_row.status, "validation": state.get("validation", {}), "claim": state.get("claim", {})}


@router.post("/claims/{claim_id}/resume", response_model=dict)
@router.post("/claims/{claim_id}/approve", response_model=dict)
@router.post("/api/claims/{claim_id}/resume", response_model=dict, include_in_schema=False)
@router.post("/api/claims/{claim_id}/approve", response_model=dict, include_in_schema=False)


async def resume_claim_pipeline(claim_id: str, payload: dict | None = None, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    request_payload = payload if isinstance(payload, dict) else {}
    corrections = request_payload.get("corrections") or {}
    if not isinstance(corrections, dict):
        corrections = {}
    reviewer = request_payload.get("reviewer", "Claim Workspace")
    stored_payload = claim_row.payload or {}
    if not isinstance(stored_payload, dict):
        stored_payload = {}
    claim_payload = _safe_claim_payload(claim_row)
    stored_pipeline = stored_payload.get("pipeline") if isinstance(stored_payload, dict) else {}
    if not isinstance(stored_pipeline, dict):
        stored_pipeline = {}

    current_statuses = {
        str(claim_row.status or "").upper(),
        str(claim_row.pipeline_state or "").upper(),
        str(claim_payload.get("status") or "").upper(),
        str(claim_payload.get("pipeline_state") or "").upper(),
        str(stored_payload.get("status") or "").upper() if isinstance(stored_payload, dict) else "",
        str(stored_payload.get("pipeline_state") or "").upper() if isinstance(stored_payload, dict) else "",
        str(stored_pipeline.get("pipeline_state") or "").upper(),
    }
    current_stage = str(
        claim_row.stage
        or claim_row.current_stage
        or claim_payload.get("stage")
        or claim_payload.get("current_stage")
        or stored_pipeline.get("current_stage")
        or ""
    ).upper()
    approval_required = bool(
        claim_row.approval_required
        or claim_payload.get("approval_required")
        or claim_payload.get("review_required")
        or stored_payload.get("approval_required")
        or stored_pipeline.get("approval_required")
        or stored_pipeline.get("review_required")
    )

    if current_statuses.intersection(CLEARINGHOUSE_WAITING_STATUSES) or (
        current_stage == "CLEARINGHOUSE" and approval_required
    ):
        try:
            accepted = await ClearinghouseOrchestrationService(db).accept(claim_id, reviewer=reviewer)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Clearinghouse approval failed: {exc}") from exc

        accepted = make_json_safe(accepted)
        return {
            "success": True,
            "claim_id": claim_id,
            "message": "Clearinghouse accepted. Pipeline resumed.",
            "status": accepted.get("status", "PROCESSING"),
            "stage": accepted.get("stage", "ACKNOWLEDGMENT"),
            "current_stage": accepted.get("current_stage", "ACKNOWLEDGMENT"),
            "current_agent": accepted.get("current_agent", "PAYER_ACKNOWLEDGMENT"),
            "pipeline_state": accepted.get("pipeline_state", "PROCESSING"),
            "approval_required": False,
            "clearinghouse_accepted": True,
            "claim": accepted.get("claim", {}),
            "pipeline": accepted.get("pipeline", {}),
            "resumed": accepted.get("resumed", accepted),
            "downstream_job_id": accepted.get("downstream_job_id"),
        }

    if not isinstance(claim_payload.get("provider"), dict):
        claim_payload["provider"] = {}

    provider_corrections = corrections.get("provider") or {}
    if not isinstance(provider_corrections, dict):
        provider_corrections = {}

    request_provider = request_payload.get("provider") or {}
    if not isinstance(request_provider, dict):
        request_provider = {}

    provider_npi = (
        provider_corrections.get("npi")
        or corrections.get("provider_npi")
        or request_payload.get("provider_npi")
        or request_provider.get("npi")
    )

    if provider_corrections:
        claim_payload.setdefault("provider", {}).update(
            {
                key: value
                for key, value in provider_corrections.items()
                if value is not None
            }
        )

    if provider_npi:
        provider_npi = str(provider_npi).strip()
        claim_payload.setdefault("provider", {})["npi"] = provider_npi
        claim_payload["provider_npi"] = provider_npi
        missing_fields = claim_payload.get("missing_fields") or []
        claim_payload["missing_fields"] = [
            field for field in missing_fields
            if field != "provider.npi"
        ]

        if isinstance(claim_payload.get("extraction"), dict):
            extraction_missing = claim_payload["extraction"].get("missing_fields") or []
            claim_payload["extraction"]["missing_fields"] = [
                field for field in extraction_missing
                if field != "provider.npi"
            ]

        if not claim_payload["missing_fields"]:
            claim_payload["requires_human_review"] = False
            claim_payload["reason"] = None

    if claim_payload.get("provider", {}).get("npi"):
        claim_payload["provider_npi"] = claim_payload["provider"]["npi"]

    claim_payload["manual_review_approved"] = True
    claim_payload["human_approved"] = True
    claim_payload["human_approved_at"] = datetime.utcnow().isoformat()
    claim_payload["human_approved_by"] = reviewer
    processing_mode = str(
        claim_payload.get("clearinghouse_processing_mode")
        or claim_payload.get("processing_mode")
        or "MANUAL"
    ).upper()
    if processing_mode not in {"AUTO", "MANUAL"}:
        processing_mode = "MANUAL"
    claim_payload["processing_mode"] = processing_mode
    claim_payload["clearinghouse_processing_mode"] = processing_mode
    claim_payload["pipeline_paused"] = False
    claim_payload["waiting_for_human"] = False
    claim_payload["review_required"] = False
    claim_payload["queue_state"] = "RESUMED"
    claim_payload["review_status"] = "APPROVED"
    claim_payload["current_stage"] = "SUBMISSION"
    claim_payload["current_agent"] = "Submission Review"
    claim_payload["active_step"] = "submission"
    claim_payload["status"] = "PROCESSING"
    claim_payload["submission_started"] = True
    claim_payload["submission_status"] = "STARTED"
    claim_payload["progress"] = 60
    pipeline = stored_payload.setdefault("pipeline", {})
    pipeline["pipeline_paused"] = False
    pipeline["waiting_for_human"] = False
    pipeline["review_required"] = False
    pipeline["queue_state"] = "RESUMED"
    pipeline["review_status"] = "APPROVED"
    pipeline["current_stage"] = "SUBMISSION"
    pipeline["current_agent"] = "Submission Review"
    pipeline["active_step"] = "submission"
    pipeline["submission_started"] = True
    pipeline["submission_status"] = "STARTED"
    pipeline["progress"] = 60

    claim_payload.pop("payload", None)
    claim_payload.pop("claim", None)
    claim_payload.pop("_sa_instance_state", None)
    stored_payload["claim"] = make_json_safe(claim_payload)
    safe_payload = make_json_safe(stored_payload)

    if isinstance(safe_payload.get("claim"), dict):
        safe_payload["claim"].pop("payload", None)
        safe_payload["claim"].pop("claim", None)
        safe_payload["claim"].pop("_sa_instance_state", None)

    safe_claim_payload = safe_payload.get("claim", {})
    if not isinstance(safe_claim_payload, dict):
        safe_claim_payload = {}
    safe_pipeline = make_json_safe(safe_payload.get("pipeline") or pipeline)

    claim_row.status = "PROCESSING"
    claim_row.stage = "SUBMISSION"
    try:
        claim_row.payload = safe_payload
        flag_modified(claim_row, "payload")
        db.commit()
    except Exception:
        db.rollback()
        raise

    steps = (safe_payload.get("pipeline") or {}).get("steps") or {}
    service = ClearinghouseOrchestrationService(db)

    try:
        submission_state = {}
        if not steps.get("submitted") and not safe_claim_payload.get("submission"):
            await manager.broadcast({
                "event": "submission_started",
                "type": "SUBMISSION_STARTED",
                "claim_id": claim_id,
                "status": "PROCESSING",
                "stage": "SUBMISSION",
                "step": "submission",
                "current_stage": "SUBMISSION",
                "current_agent": "Submission Review",
                "active_step": "submission",
                "queue_state": "RESUMED",
                "pipeline_paused": False,
                "submission_started": True,
                "submission_status": "STARTED",
                "progress": 60,
                "pipeline": safe_pipeline,
                "claim": make_json_safe(safe_claim_payload),
                "reviewer": reviewer,
                "timestamp": datetime.utcnow().isoformat(),
            })
            submission_state = await SubmissionAgent().run(safe_claim_payload)
            claim_payload = make_json_safe(submission_state.get("claim", safe_claim_payload))
            claim_payload["manual_review_approved"] = True
            claim_payload["human_approved"] = True
        else:
            claim_payload = make_json_safe(safe_claim_payload)
            submission_state = {
                "claim": claim_payload,
                "status": claim_payload.get("status"),
                "pipeline_state": claim_payload.get("pipeline_state"),
                "pipeline": safe_pipeline,
            }

        queued = service.queue_after_submission(
            claim_id,
            claim_payload,
            clearinghouse_response=claim_payload.get("submission") or {"status": "PENDING"},
            reviewer=reviewer,
        )
        resumed_status = str(
            submission_state.get("status")
            or submission_state.get("pipeline_state")
            or queued.get("status")
            or queued.get("pipeline_state")
            or claim_payload.get("status")
            or claim_payload.get("pipeline_state")
            or ""
        ).upper()

        if processing_mode == "MANUAL" and resumed_status in CLEARINGHOUSE_WAITING_STATUSES:
            waiting_claim = make_json_safe(queued.get("claim") or claim_payload)
            waiting_pipeline = make_json_safe(queued.get("pipeline") or claim_payload.get("pipeline", {}))
            await manager.broadcast({
                "event": "clearinghouse_queued",
                "type": "clearinghouse_queued",
                "claim_id": claim_id,
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "stage": "CLEARINGHOUSE",
                "step": "clearinghouse",
                "agent": "CLEARINGHOUSE",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "review_required": True,
                "processing_mode": processing_mode,
                "pipeline": waiting_pipeline,
                "claim": waiting_claim,
                "reviewer": reviewer,
                "timestamp": datetime.utcnow().isoformat(),
            })
            return {
                "success": True,
                "claim_id": claim_id,
                "message": "HITL approved. Claim submitted and queued for clearinghouse review.",
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "review_required": True,
                "processing_mode": processing_mode,
                "queued": make_json_safe(queued),
                "resumed": make_json_safe(submission_state),
                "claim": waiting_claim,
                "pipeline": waiting_pipeline,
            }

        if processing_mode != "AUTO":
            return {
                "success": True,
                "claim_id": claim_id,
                "message": "HITL approved. Claim submitted and queued for clearinghouse review.",
                "status": "WAITING_FOR_APPROVAL",
                "pipeline_state": "WAITING_FOR_APPROVAL",
                "current_stage": "CLEARINGHOUSE",
                "current_agent": "CLEARINGHOUSE",
                "active_step": "clearinghouse",
                "review_required": True,
                "processing_mode": processing_mode,
                "queued": make_json_safe(queued),
                "resumed": make_json_safe(submission_state),
                "claim": make_json_safe(queued.get("claim") or claim_payload),
                "pipeline": make_json_safe(queued.get("pipeline") or claim_payload.get("pipeline", {})),
            }

        resumed = await service.auto_accept_if_qualified(claim_id, reviewer=reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}") from exc

    await manager.broadcast({
        "event": "pipeline_resumed",
        "type": "pipeline_resumed",
        "claim_id": claim_id,
        "status": resumed.get("status", "PROCESSING"),
        "stage": "CLEARINGHOUSE_PENDING",
        "step": "clearinghouse",
        "agent": "CLEARINGHOUSE",
        "pipeline": make_json_safe(resumed.get("pipeline", {})),
        "claim": make_json_safe(resumed.get("claim", claim_payload)),
        "reviewer": reviewer,
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {
        "success": True,
        "claim_id": claim_id,
        "message": "Claim accepted; pipeline resumed from clearinghouse",
        "queued": make_json_safe(queued),
        "resumed": make_json_safe(resumed),
        "status": resumed.get("status", "PROCESSING"),
        "pipeline": make_json_safe(resumed.get("pipeline", {})),
        "claim": make_json_safe(resumed.get("claim", claim_payload)),
    }


@router.post("/claims/{claim_id}/reject", response_model=dict)
@router.post("/api/claims/{claim_id}/reject", response_model=dict, include_in_schema=False)
async def reject_claim_pipeline(claim_id: str, payload: dict | None = None, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    reviewer = (payload or {}).get("reviewer", "Claim Workspace")
    reason = (payload or {}).get("reason", "Rejected during manual review")
    stored_payload = claim_row.payload or {}
    claim_payload = _safe_claim_payload(claim_row)
    finalized_at = datetime.utcnow().isoformat()

    claim_payload.update({
        "status": "REJECTED",
        "workspace": "COMMAND_CENTER",
        "finalized_at": finalized_at,
        "pipeline_paused": False,
        "waiting_for_human": False,
        "review_required": False,
        "review_status": "REJECTED",
        "queue_state": "REJECTED",
        "current_stage": "HARD_REJECT",
        "current_agent": "Manual Review",
        "active_step": "manual_reject",
        "rejection_reason": reason,
        "rejected_by": reviewer,
        "rejected_at": finalized_at,
        "progress": 100,
        "submission_started": False,
        "submission_status": "REJECTED",
    })
    pipeline = stored_payload.setdefault("pipeline", {})
    pipeline.update({
        "pipeline_state": "HARD_REJECT",
        "pipeline_status": "REJECTED",
        "pipeline_paused": False,
        "current_stage": "HARD_REJECT",
        "current_agent": "Manual Review",
        "active_step": "manual_reject",
        "queue_state": "REJECTED",
        "review_status": "REJECTED",
        "progress": 100,
    })
    stored_payload.update({
        "claim": claim_payload,
        "workspace": "COMMAND_CENTER",
        "finalized_at": finalized_at,
        "manual_rejection": {"reason": reason, "reviewer": reviewer, "timestamp": finalized_at},
    })
    claim_row.status = "REJECTED"
    claim_row.stage = "HARD_REJECT"
    claim_row.payload = stored_payload
    flag_modified(claim_row, "payload")
    db.commit()

    try:
        log_audit(claim_id, "REJECT_CLAIM", "REJECTED", {"reason": reason, "reviewer": reviewer})
    except Exception:
        pass

    event = {
        "event": "claim_rejected",
        "type": "claim_rejected",
        "claim_id": claim_id,
        "status": "REJECTED",
        "workspace": "COMMAND_CENTER",
        "current_stage": "HARD_REJECT",
        "current_agent": "Manual Review",
        "active_step": "manual_reject",
        "pipeline": pipeline,
        "claim": claim_payload,
        "reason": reason,
        "reviewer": reviewer,
        "timestamp": finalized_at,
    }
    await manager.broadcast(event)
    await manager.broadcast({
        **event,
        "event": "claim_completed",
        "type": "claim_completed",
    })
    return {"success": True, "claim_id": claim_id, "status": "REJECTED", "claim": claim_payload, "pipeline": pipeline}


@router.get("/claims/{claim_id}/denial-analysis", response_model=dict)
async def get_denial_analysis(claim_id: str, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    payload = claim_row.payload or {}
    claim_payload = _safe_claim_payload(claim_row)
    existing = payload.get("denial_ai") or claim_payload.get("denial_ai")
    if existing:
        return {"claim_id": claim_id, "analysis": existing}

    denial = payload.get("denial") or claim_payload.get("denial_risk") or {}
    state = await LLMDenialAgent().run(claim_payload, denial)
    analysis = state.get("denial_ai", {})
    payload["claim"] = state.get("claim", claim_payload)
    payload["denial_ai"] = analysis
    claim_row.payload = payload
    flag_modified(claim_row, "payload")
    db.commit()
    return {"claim_id": claim_id, "analysis": analysis}


@router.post("/claims/{claim_id}/generate-appeal", response_model=dict)
async def generate_appeal(claim_id: str, payload: dict | None = None, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    claim_payload = _safe_claim_payload(claim_row)
    denial = (claim_row.payload or {}).get("denial") or claim_payload.get("denial_risk") or {}
    state = await LLMDenialAgent().run(claim_payload, denial)
    analysis = state.get("denial_ai", {})
    appeal = state.get("appeal", {})
    payer = claim_payload.get("payer", {})

    db.add(AppealHistory(
        claim_id=claim_id,
        payer=payer.get("name"),
        denial_code=analysis.get("denial_code"),
        denial_reason=analysis.get("denial_reason") or analysis.get("root_cause"),
        appeal_text=appeal.get("appeal_text") or analysis.get("appeal_text"),
        status="DRAFT",
        retry_probability=float(analysis.get("retry_probability") or 0),
        analysis=analysis,
    ))

    stored_payload = claim_row.payload or {}
    stored_payload["claim"] = state.get("claim", claim_payload)
    stored_payload["denial_ai"] = analysis
    stored_payload["appeal"] = appeal
    claim_row.payload = stored_payload
    flag_modified(claim_row, "payload")
    db.commit()

    return {"claim_id": claim_id, "analysis": analysis, "appeal": appeal}


@router.post("/claims/{claim_id}/retry-submission", response_model=dict)
async def retry_submission(claim_id: str, payload: dict | None = None, db: Session = Depends(get_db)):
    claim_row = _get_claim_or_404(claim_id, db)
    stored_payload = claim_row.payload or {}
    claim_payload = _safe_claim_payload(claim_row)
    analysis = stored_payload.get("denial_ai") or claim_payload.get("denial_ai") or {}
    corrected_claim = LLMDenialAgent().auto_fix(claim_payload, analysis)
    corrected_claim["status"] = "READY_FOR_RESUBMISSION"
    corrected_claim["resubmission_required"] = True
    stored_payload["claim"] = corrected_claim
    stored_payload["retry_submission"] = {
        "status": "READY_FOR_RESUBMISSION",
        "created_at": datetime.utcnow().isoformat(),
        "strategy": analysis.get("resubmission_strategy"),
    }
    claim_row.payload = stored_payload
    flag_modified(claim_row, "payload")
    claim_row.status = "RESUBMITTED"
    db.add(LearningMetrics(
        claim_id=claim_id,
        denial_patterns=[analysis.get("category") or analysis.get("denial_reason")],
        correction_history={"denial_ai_retry": analysis.get("suggested_corrections", [])},
        confidence_trends={"retry_probability": analysis.get("retry_probability", 0)},
        improvement_signals={"payer_intelligence": analysis.get("payer_rule_findings", [])},
    ))
    db.commit()

    queued = await ClearinghouseOrchestrationService(db).repair_and_resubmit(claim_id, reviewer=(payload or {}).get("reviewer", "SYSTEM"))
    await manager.broadcast({"event": "claim_resubmitted", "type": "claim_resubmitted", "claim_id": claim_id, "status": queued.get("status")})
    return {
        "claim_id": claim_id,
        "status": queued.get("status", "PENDING_CLEARINGHOUSE"),
        "claim": queued.get("claim", corrected_claim),
        "resubmission_strategy": analysis.get("resubmission_strategy"),
        "clearinghouse": queued.get("clearinghouse", {}),
    }


@router.put("/claims/{claim_id}/clearinghouse-mode", response_model=dict)
async def set_clearinghouse_mode(claim_id: str, payload: dict, db: Session = Depends(get_db)):
    mode = str(payload.get("processing_mode") or payload.get("mode") or "MANUAL").upper()
    reviewer = payload.get("reviewer", "Claim Workspace")
    try:
        result = ClearinghouseOrchestrationService(db).set_processing_mode(claim_id, mode, reviewer=reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await manager.broadcast({
        "event": "clearinghouse_mode_changed",
        "type": "clearinghouse_mode_changed",
        "claim_id": claim_id,
        "processing_mode": mode,
        "status": result.get("status"),
    })
    return result


@router.post("/claims/{claim_id}/clearinghouse-auto-review", response_model=dict)
@router.post("/api/claims/{claim_id}/clearinghouse-auto-review", response_model=dict, include_in_schema=False)
async def run_clearinghouse_auto_review(claim_id: str, payload: dict | None = None, db: Session = Depends(get_db)):
    service = ClearinghouseOrchestrationService(db)
    reviewer = (payload or {}).get("reviewer", "AI Auto Review")
    try:
        service.set_processing_mode(claim_id, "AUTO", reviewer=reviewer)
        result = await service.auto_accept_if_qualified(claim_id, reviewer=reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        **result,
        "status": "AUTO_ACCEPTED" if result.get("auto_accept") else result.get("status"),
        "final_status": result.get("status"),
        "decision": result.get("decision"),
        "claim": result,
    }


@router.post("/claims/{claim_id}/hitl-case", response_model=dict)
async def create_or_get_hitl_case(
    claim_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
):
    case_service = CaseService(db)
    body = payload or {}

    existing = case_service.get_case_by_claim(claim_id)

    if existing:
        data = case_service.serialize_case(existing, include_children=False)

        case_id = data.get("case_id") or data.get("id")

        return {
            "claim_id": claim_id,
            "case_id": case_id,
            "status": data.get("status") or "OPEN",
            "case": data,
            "hitl_case": data,
            "message": "Existing HITL case returned",
        }

    claim = _get_claim_or_404(claim_id, db)
    claim_payload = _safe_claim_payload(claim)

    reason = (
        body.get("reason")
        or claim_payload.get("failure_reason")
        or claim_payload.get("authorization_reason")
        or claim_payload.get("denial_reason")
        or "Manual review required from Claim Workspace"
    )

    validation_result = {}
    route = {}

    try:
        validation_result = validate_claim_enterprise(claim, db) or {}
    except Exception as exc:
        validation_result = {
            "status": "VALIDATION_SKIPPED",
            "error": str(exc),
        }

    try:
        route = route_case_for_claim(claim, validation_result) or {}
    except Exception as exc:
        route = {
            "assigned_team": "MA Team",
            "next_stage": "CASE_ORCHESTRATOR",
            "priority": "HIGH",
            "routing_error": str(exc),
        }

    assigned_role = (
        body.get("assigned_role")
        or body.get("assigned_team")
        or route.get("assigned_team")
        or "MA Team"
    )

    try:
        risk_score = get_risk_score(claim_payload)
    except Exception:
        risk_score = 0

    priority = (
        body.get("priority")
        or route.get("priority")
        or ("HIGH" if float(risk_score or 0) >= 70 else "MEDIUM")
    )

    try:
        confidence = float(
            body.get("confidence")
            or claim_payload.get("confidence")
            or claim_payload.get("extraction_confidence")
            or 0
        )
    except Exception:
        confidence = 0.0

    try:
        confidence_score = float(
            body.get("confidence_score")
            or claim_payload.get("confidence_score")
            or claim_payload.get("extraction_confidence")
            or confidence
            or 0
        )
    except Exception:
        confidence_score = confidence

    metadata = {
        "source": "claim_workspace",
        "routing": route,
        "validation_result": validation_result,
    }

    if isinstance(body.get("metadata"), dict):
        metadata.update(body["metadata"])

    try:
        case = case_service.create_case(
            CaseCreate(
                claim_id=claim_id,
                title=body.get("title") or f"HITL review for {claim_id}",
                description=body.get("description") or reason,
                case_type=body.get("case_type") or "HITL",
                priority=priority,
                assigned_role=assigned_role,
                assigned_team=body.get("assigned_team") or assigned_role,
                assigned_to=body.get("assigned_to"),
                next_stage=body.get("next_stage") or route.get("next_stage") or "CASE_ORCHESTRATOR",
                created_by=body.get("created_by") or "Claim Workspace",
                denial_reason=reason,
                ai_suggestion=body.get("ai_suggestion") or claim_payload.get("ai_suggestion"),
                risk_score=risk_score,
                confidence=confidence,
                template_name=body.get("template_name") or claim_payload.get("claim_type") or "HITL",
                confidence_score=confidence_score,
                extraction_quality=body.get("extraction_quality") or claim_payload.get("extraction_quality") or "unknown",
                metadata=metadata,
            )
        )
    except Exception as exc:
        # If create failed due to race/duplicate, try reading again before returning 500.
        existing = case_service.get_case_by_claim(claim_id)

        if existing:
            data = case_service.serialize_case(existing, include_children=False)
            case_id = data.get("case_id") or data.get("id")

            return {
                "claim_id": claim_id,
                "case_id": case_id,
                "status": data.get("status") or "OPEN",
                "case": data,
                "hitl_case": data,
                "message": "Existing HITL case returned after create conflict",
            }

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create HITL case: {str(exc)}",
        )

    data = case_service.serialize_case(case, include_children=False)
    case_id = data.get("case_id") or data.get("id")

    await manager.broadcast(
        {
            "event": "case_created",
            "type": "case_created",
            "case": data,
            "hitl_case": data,
            "case_id": case_id,
            "claim_id": claim_id,
            "status": data.get("status") or "OPEN",
            "review_required": True,
            "approval_required": True,
            "pipeline_paused": True,
        }
    )

    return {
        "claim_id": claim_id,
        "case_id": case_id,
        "status": data.get("status") or "OPEN",
        "case": data,
        "hitl_case": data,
        "message": "HITL case created",
    }


@router.get("/claims/{claim_id}/cms1500")
async def download_cms1500(claim_id: str, db: Session = Depends(get_db)):
    path = _artifact_file(_get_claim_or_404(claim_id, db), "cms1500")
    return FileResponse(path, media_type="application/pdf", filename=f"{claim_id}-CMS1500.pdf")


@router.get("/claims/{claim_id}/ub04")
async def download_ub04(claim_id: str, db: Session = Depends(get_db)):
    path = _artifact_file(_get_claim_or_404(claim_id, db), "ub04")
    return FileResponse(path, media_type="application/pdf", filename=f"{claim_id}-UB04.pdf")


@router.get("/claims/{claim_id}/edi")
async def download_edi(claim_id: str, db: Session = Depends(get_db)):
    path = _artifact_file(_get_claim_or_404(claim_id, db), "edi")
    return FileResponse(path, media_type="text/plain", filename=f"{claim_id}.edi")


@router.get("/command-center/claims", response_model=dict)
async def get_command_center_claims(
    search: str = "",
    status: str = "",
    payer: str = "",
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Claim)
    rows = query.order_by(Claim.updated_at.desc()).all()
    finalized = []
    for row in rows:
        payload = row.payload or {}
        claim_payload = payload.get("claim", payload)
        row_status = str(row.status or claim_payload.get("status") or "").upper()
        workspace = str(claim_payload.get("workspace") or payload.get("workspace") or "").upper()
        if row_status not in FINAL_CLAIM_STATUSES and workspace != "COMMAND_CENTER":
            continue
        item = _serialize_command_claim(row)
        if status and str(item.get("status", "")).upper() != status.upper():
            continue
        payer_name = item.get("payer", {}).get("name") if isinstance(item.get("payer"), dict) else item.get("payer")
        if payer and payer.upper() not in str(payer_name or "").upper():
            continue
        if search:
            blob = f"{item.get('claim_id')} {item.get('patient', {}).get('name')} {payer_name}".lower()
            if search.lower() not in blob:
                continue
        finalized.append(item)

    start = max(page - 1, 0) * limit
    end = start + limit
    return {
        "status": "SUCCESS",
        "count": len(finalized),
        "page": page,
        "limit": limit,
        "claims": finalized[start:end],
    }


@router.get("/command-center/claims/{claim_id}", response_model=dict)
async def get_command_center_claim(claim_id: str, db: Session = Depends(get_db)):
    claim = _get_claim_or_404(claim_id, db)
    events = (
        db.query(PipelineEvent)
        .filter(PipelineEvent.claim_id == claim_id)
        .order_by(PipelineEvent.timestamp.asc())
        .all()
    )
    data = _serialize_command_claim(claim, include_detail=True)
    data["audit_history"] = data.get("audit_history") or [_serialize_event(event) for event in events]
    data["events"] = [_serialize_event(event) for event in events]
    return data

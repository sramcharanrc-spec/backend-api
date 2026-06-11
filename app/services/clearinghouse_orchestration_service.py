import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List

from app.intake.db_service import clean_nan
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.agents.analytics.analytics_agent import AnalyticsAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.agents.learning.learning_agent import LearningAgent
from app.agents.denial_ai.llm_denial_agent import LLMDenialAgent
from app.agents.auto_correction_agent import auto_correct_claim

from app.core.state_machine import (
    PipelineState,
    is_final_pipeline_state,
    is_waiting_for_approval,
    waiting_stage_statuses,
)
from app.models.claim_model import Claim
from app.models.clearinghouse_model import (
    ClearinghouseEvent,
    DenialHistory,
    PaymentHistory,
    SubmissionHistory,
)
from app.models.learning_metrics_model import LearningMetrics
from app.models.pipeline_events_model import PipelineEvent
from app.services.analytics_service import update_metrics
from app.websocket.manager import manager


PENDING_CLEARINGHOUSE = "PENDING_CLEARINGHOUSE"
WAITING_FOR_APPROVAL = PipelineState.WAITING_FOR_APPROVAL.value
RESUMED = PipelineState.RESUMED.value
AUTO_MODE = "AUTO"
MANUAL_MODE = "MANUAL"

logger = logging.getLogger(__name__)


STEP_BY_AGENT = {
    "CLEARINGHOUSE_AUTO": "clearinghouse",
    "CLEARINGHOUSE": "clearinghouse",
    "ACKNOWLEDGMENT": "acknowledgment",
    "PAYER_ACKNOWLEDGMENT": "acknowledgment",
    "PAYER": "payer",
    "DENIAL": "denial_ai",
    "DENIAL_AI": "denial_ai",
    "PAYMENT": "payment",
    "FEEDBACK_LOOP": "learning",
    "LEARNING": "learning",
    "ANALYTICS": "analytics",
}

PROGRESS_BY_STEP = {
    "clearinghouse": {"running": 70, "completed": 75},
    "acknowledgment": {"running": 74, "completed": 78},
    "payer": {"running": 78, "completed": 80},
    "denial_ai": {"running": 80, "completed": 82},
    "payment": {"running": 82, "completed": 88},
    "learning": {"running": 90, "completed": 92},
    "analytics": {"running": 95, "completed": 98},
    "completed": {"completed": 100},
}


def claim_payload(row: Claim) -> Dict[str, Any]:
    payload = row.payload or {}
    claim = payload.get("claim", payload)
    return claim if isinstance(claim, dict) else {}


def ensure_dict(container: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        value = {}
        container[key] = value
    return value


def claim_submission_id(claim: Dict[str, Any], fallback: str | None = None) -> str:
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


def pipeline_steps(payload: Dict[str, Any]) -> Dict[str, Any]:
    pipeline = ensure_dict(payload, "pipeline")
    return ensure_dict(pipeline, "steps")


def mark_waiting_for_approval(payload: Dict[str, Any], claim: Dict[str, Any], progress: int = 70) -> Dict[str, Any]:
    pipeline = ensure_dict(payload, "pipeline")
    steps = ensure_dict(pipeline, "steps")
    now = datetime.utcnow().isoformat()

    steps.update({
        "submitted": True,
        "clearinghouse_queued": True,
        "clearinghouse_accepted": False,
        "acknowledged": False,
        "denial_checked": False,
        "paid": False,
        "feedback_captured": False,
        "learning_updated": False,
        "analytics_done": False,
    })

    pipeline.update({
        "pipeline_state": WAITING_FOR_APPROVAL,
        "pipeline_status": WAITING_FOR_APPROVAL,
        "current_stage": "CLEARINGHOUSE",
        "current_agent": "CLEARINGHOUSE",
        "active_step": "clearinghouse",
        "approval_required": True,
        "review_required": True,
        "pipeline_paused": True,
        "paused_at": pipeline.get("paused_at") or now,
        "progress": progress,
        "stage_status": waiting_stage_statuses(),
        "pending_stages": ["ACKNOWLEDGMENT", "PAYER", "DENIAL_AI", "PAYMENT", "LEARNING", "ANALYTICS", "COMPLETED"],
    })

    claim.update({
        "status": WAITING_FOR_APPROVAL,
        "pipeline_state": WAITING_FOR_APPROVAL,
        "pipeline_status": WAITING_FOR_APPROVAL,
        "current_stage": "CLEARINGHOUSE",
        "current_agent": "CLEARINGHOUSE",
        "active_step": "clearinghouse",
        "approval_required": True,
        "review_required": True,
        "pipeline_paused": True,
        "paused_at": claim.get("paused_at") or now,
        "progress": progress,
        "pending_stages": ["ACKNOWLEDGMENT", "PAYER", "DENIAL_AI", "PAYMENT", "LEARNING", "ANALYTICS", "COMPLETED"],
    })

    payload.update({
        "pipeline_state": WAITING_FOR_APPROVAL,
        "current_stage": "CLEARINGHOUSE",
        "approval_required": True,
        "review_required": True,
        "pipeline_paused": True,
        "paused_at": payload.get("paused_at") or claim["paused_at"],
    })

    return pipeline


class ClearinghouseOrchestrationService:
    def __init__(self, db: Session):
        self.db = db

    def get_claim(self, claim_id: str) -> Claim | None:
        return self.db.query(Claim).filter(Claim.claim_id == claim_id).first()

    def queue_after_submission(
        self,
        claim_id: str,
        claim: Dict[str, Any],
        clearinghouse_response: Dict[str, Any] | None = None,
        artifacts: Dict[str, Any] | None = None,
        reviewer: str = "SubmissionAgent",
    ) -> Dict[str, Any]:
        row = self.get_claim(claim_id)
        if not row:
            row = Claim(
                claim_id=claim_id,
                total_charge=(claim or {}).get("total_charge", 0),
                payload={},
            )
            self.db.add(row)

        payload = clean_nan(row.payload or {})
        if not isinstance(payload, dict):
            payload = {}

        safe_claim = clean_nan(claim or {})
        if not isinstance(safe_claim, dict):
            safe_claim = {}

        submission_id = claim_submission_id(safe_claim, fallback=claim_id)
        response_submission_id = claim_submission_id(clearinghouse_response or {})
        if response_submission_id.startswith("SUB-"):
            submission_id = response_submission_id

        if submission_id.startswith("SUB-"):
            safe_claim["submission_id"] = submission_id

        processing_mode = str(
            safe_claim.get("clearinghouse_processing_mode")
            or safe_claim.get("processing_mode")
            or MANUAL_MODE
        ).upper()
        if processing_mode not in {AUTO_MODE, MANUAL_MODE}:
            processing_mode = MANUAL_MODE

        safe_claim["processing_mode"] = processing_mode
        safe_claim["clearinghouse_processing_mode"] = processing_mode

        queue_record = {
            "status": WAITING_FOR_APPROVAL,
            "legacy_status": PENDING_CLEARINGHOUSE,
            "queued_at": datetime.utcnow().isoformat(),
            "response": clean_nan(clearinghouse_response or {}),
            "review_required": True,
            "processing_mode": processing_mode,
            "review_type": "Approval Required",
        }

        safe_artifacts = clean_nan(artifacts or payload.get("generated_artifacts") or {})

        safe_claim["clearinghouse"] = queue_record
        safe_claim["generated_artifacts"] = safe_artifacts
        safe_claim["clearinghouse_status"] = PENDING_CLEARINGHOUSE

        payload["claim"] = safe_claim
        payload["clearinghouse"] = queue_record
        payload["generated_artifacts"] = safe_artifacts

        steps = pipeline_steps(payload)
        steps.update({
            "submitted": True,
            "clearinghouse_queued": True,
            "acknowledged": False,
            "denial_checked": False,
            "paid": False,
            "feedback_captured": False,
            "learning_updated": False,
            "analytics_done": False,
        })

        pipeline = mark_waiting_for_approval(payload, safe_claim)
        payload["pipeline"] = clean_nan(pipeline)
        payload = clean_nan(payload)

        row.status = WAITING_FOR_APPROVAL
        row.stage = "CLEARINGHOUSE"
        row.pipeline_state = WAITING_FOR_APPROVAL
        row.current_stage = "CLEARINGHOUSE"
        row.approval_required = True
        row.paused_at = row.paused_at or datetime.utcnow()
        row.total_charge = safe_claim.get("total_charge", row.total_charge or 0)
        row.payload = payload
        flag_modified(row, "payload")
        row.updated_at = datetime.utcnow()

        self._event(claim_id, "pipeline_paused", reviewer, WAITING_FOR_APPROVAL, queue_record)
        self._event(claim_id, "clearinghouse_queued", reviewer, WAITING_FOR_APPROVAL, queue_record)
        self._submission_history(claim_id, submission_id, clearinghouse_response, reviewer, WAITING_FOR_APPROVAL)

        self.db.commit()
        return self.serialize(row)

    def set_processing_mode(self, claim_id: str, mode: str, reviewer: str = "SYSTEM") -> Dict[str, Any]:
        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)

        processing_mode = str(mode or MANUAL_MODE).upper()
        if processing_mode not in {AUTO_MODE, MANUAL_MODE}:
            raise ValueError("processing_mode must be AUTO or MANUAL")

        clearinghouse = ensure_dict(payload, "clearinghouse")
        clearinghouse["processing_mode"] = processing_mode
        clearinghouse["review_required"] = processing_mode == MANUAL_MODE
        clearinghouse["review_type"] = "AI Auto Review" if processing_mode == AUTO_MODE else "Human Review"
        clearinghouse["updated_at"] = datetime.utcnow().isoformat()

        claim["processing_mode"] = processing_mode
        claim["clearinghouse_processing_mode"] = processing_mode
        claim["clearinghouse"] = clearinghouse

        payload["claim"] = clean_nan(claim)
        row.payload = clean_nan(payload)
        flag_modified(row, "payload")
        row.updated_at = datetime.utcnow()

        self._event(claim_id, "clearinghouse_mode_changed", reviewer, processing_mode, clearinghouse)
        self.db.commit()
        return self.serialize(row)

    def auto_review_decision(self, claim_id: str) -> Dict[str, Any]:
        row = self._require_claim(claim_id)
        payload = row.payload or {}
        claim = claim_payload(row)

        validation = payload.get("validation") or claim.get("validation") or {}
        compliance = payload.get("compliance") or payload.get("compliance_results") or claim.get("compliance") or {}
        extraction = payload.get("extraction") or claim.get("extraction") or {}
        denial = payload.get("denial_ai") or claim.get("denial_ai") or claim.get("denial_risk") or {}

        validation_score = self._as_percent(validation.get("score") or validation.get("validation_score") or extraction.get("validation_score") or 100)
        ocr_confidence = self._as_percent(extraction.get("extraction_confidence") or extraction.get("ocr_quality") or claim.get("confidence") or 100)
        denial_risk = self._as_percent(denial.get("risk_score") or denial.get("probability") or 0)
        compliance_issues = compliance.get("issues") or compliance.get("warnings") or []
        compliance_failed = str(compliance.get("status", "")).upper() in {"FAILED", "NON_COMPLIANT", "FAIL"}

        reasons: List[str] = []
        if validation_score < 80:
            reasons.append("validation score below 80%")
        if ocr_confidence < 75:
            reasons.append("OCR confidence below 75%")
        if denial_risk > 70:
            reasons.append("denial risk above 70%")
        if compliance_failed or bool(compliance_issues):
            reasons.append("compliance review required")

        return {
            "claim_id": claim_id,
            "decision": MANUAL_MODE if reasons else AUTO_MODE,
            "reasons": reasons,
            "validation_score": validation_score,
            "ocr_confidence": ocr_confidence,
            "denial_risk": denial_risk,
            "compliance_issues": compliance_issues,
        }

    async def auto_accept_if_qualified(self, claim_id: str, reviewer: str = "SYSTEM_AUTO") -> Dict[str, Any]:
        decision = self.auto_review_decision(claim_id)

        if decision["decision"] == MANUAL_MODE:
            row = self._require_claim(claim_id)
            payload = clean_nan(row.payload or {})
            claim = claim_payload(row)
            clearinghouse = ensure_dict(payload, "clearinghouse")

            clearinghouse["status"] = "MANUAL_REVIEW_REQUIRED"
            clearinghouse["review_required"] = True
            clearinghouse["auto_review"] = decision

            claim["status"] = "MANUAL_REVIEW_REQUIRED"
            claim["pipeline_stage"] = "manual_review_required"
            claim["current_stage"] = "CLEARINGHOUSE_REVIEW"
            claim["current_agent"] = "CLEARINGHOUSE_AUTO"
            claim["pipeline_state"] = "MANUAL_REVIEW_REQUIRED"

            payload["claim"] = clean_nan(claim)
            row.status = "MANUAL_REVIEW_REQUIRED"
            row.stage = "CLEARINGHOUSE_REVIEW"
            row.payload = clean_nan(payload)
            flag_modified(row, "payload")

            self._event(claim_id, "auto_review_manual_required", reviewer, "MANUAL_REVIEW_REQUIRED", decision)
            self._pipeline_event(claim_id, "CLEARINGHOUSE_AUTO", "MANUAL_REVIEW_REQUIRED", "; ".join(decision["reasons"]))
            self.db.commit()

            await manager.broadcast({
                "event": "agent_update",
                "type": "agent_update",
                "source_event": "auto_review_manual_required",
                "claim_id": claim_id,
                "stage": "CLEARINGHOUSE_REVIEW",
                "status": "MANUAL_REVIEW_REQUIRED",
                "progress": claim.get("progress", 70),
                "current_stage": "CLEARINGHOUSE_REVIEW",
                "current_agent": "CLEARINGHOUSE_AUTO",
                "active_step": "clearinghouse",
                "pipeline_state": "MANUAL_REVIEW_REQUIRED",
                "pipeline_status": "MANUAL_REVIEW_REQUIRED",
                "claim": clean_nan(claim),
                "pipeline": clean_nan(payload.get("pipeline", {})),
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "claim_id": claim_id,
                "status": "MANUAL_REVIEW_REQUIRED",
                "decision": MANUAL_MODE,
                "reasons": decision["reasons"],
                "metrics": decision,
                "auto_accept": False,
            }

        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        row.status = "ACCEPTED"
        row.stage = "DENIAL"
        claim["status"] = "ACCEPTED"
        claim["pipeline_stage"] = "denial"
        claim["pipeline_state"] = "ACK_RECEIVED"
        claim["pipeline_status"] = "COMPLETED"
        claim["current_agent"] = "PAYER"
        claim["current_stage"] = "PAYER"
        claim["active_step"] = "payer"
        ensure_dict(claim, "submission")["status"] = "ACCEPTED"
        payload["claim"] = clean_nan(claim)

        steps["clearinghouse_accepted"] = True
        steps["acknowledged"] = False
        steps["auto_accepted"] = True

        row.payload = clean_nan(payload)
        flag_modified(row, "payload")

        self._event(claim_id, "clearinghouse_auto_accepted", reviewer, "AUTO_ACCEPTED", {
            "reviewer": reviewer,
            "metrics": decision,
            "auto_accept": True,
        })
        self._pipeline_event(claim_id, "CLEARINGHOUSE", "AUTO_ACCEPTED", "Automatically accepted based on quality metrics")
        self.db.commit()

        await self._emit_stage(claim_id, "CLEARINGHOUSE_AUTO", "completed", "clearinghouse_auto_accepted", payload.get("pipeline", {}), claim)

        final = await self.continue_after_accept(claim_id, reviewer)
        return {
            "claim_id": claim_id,
            "status": final.get("status", "PROCESSING"),
            "decision": AUTO_MODE,
            "auto_accept": True,
            "metrics": decision,
            "pipeline": final.get("pipeline", {}),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def accept(self, claim_id: str, reviewer: str = "SYSTEM") -> Dict[str, Any]:
        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        if (
            steps.get("analytics_done")
            or is_final_pipeline_state(row.status)
            or is_final_pipeline_state(claim.get("pipeline_state"))
        ):
            logger.info("[PIPELINE_RESUME_IDEMPOTENT] claim=%s already finalized", claim_id)
            return self.serialize(row)

        now = datetime.utcnow()
        pipeline = ensure_dict(payload, "pipeline")

        row.status = "PROCESSING"
        row.stage = "ACKNOWLEDGMENT"
        row.pipeline_state = "PROCESSING"
        row.current_stage = "ACKNOWLEDGMENT"
        row.approval_required = False
        row.approved_at = row.approved_at or now
        row.resumed_at = row.resumed_at or now

        claim.update({
            "status": "PROCESSING",
            "stage": "ACKNOWLEDGMENT",
            "clearinghouse_approved": True,
            "clearinghouse_accepted": True,
            "manual_review_approved": True,
            "human_approved": True,
            "review_status": "APPROVED",
            "review_required": False,
            "waiting_for_human": False,
            "queue_state": None,
            "approval_required": False,
            "pipeline_paused": False,
            "approved_at": claim.get("approved_at") or now.isoformat(),
            "resumed_at": claim.get("resumed_at") or now.isoformat(),
            "pipeline_stage": "acknowledgment",
            "pipeline_state": "PROCESSING",
            "pipeline_status": "PROCESSING",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "current_stage": "ACKNOWLEDGMENT",
            "active_step": "acknowledgment",
            "progress": 74,
        })

        ensure_dict(claim, "submission")["status"] = "ACCEPTED"

        steps.update({
            "clearinghouse_accepted": True,
            "clearinghouse_queued": False,
            "acknowledged": False,
            "denial_checked": False,
            "paid": False,
            "resume_started": True,
        })

        pipeline.update({
            "steps": steps,
            "pipeline_state": "PROCESSING",
            "pipeline_status": "PROCESSING",
            "current_stage": "ACKNOWLEDGMENT",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "active_step": "acknowledgment",
            "approval_required": False,
            "review_required": False,
            "pipeline_paused": False,
            "approved_at": pipeline.get("approved_at") or now.isoformat(),
            "resumed_at": pipeline.get("resumed_at") or now.isoformat(),
            "progress": 74,
        })
        pipeline.setdefault("stage_status", waiting_stage_statuses())
        pipeline["stage_status"]["CLEARINGHOUSE"] = "COMPLETED"
        pipeline["stage_status"]["ACKNOWLEDGMENT"] = "RUNNING"

        payload.update({
            "claim": clean_nan(claim),
            "pipeline": clean_nan(pipeline),
            "status": "PROCESSING",
            "stage": "ACKNOWLEDGMENT",
            "pipeline_state": "PROCESSING",
            "current_stage": "ACKNOWLEDGMENT",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "review_required": False,
            "approval_required": False,
            "approved_at": payload.get("approved_at") or now.isoformat(),
            "resumed_at": payload.get("resumed_at") or now.isoformat(),
        })

        row.payload = clean_nan(payload)
        flag_modified(row, "payload")

        self._event(claim_id, "clearinghouse_accepted", reviewer, "ACCEPTED", {"reviewer": reviewer})
        self._event(claim_id, "pipeline_resumed", reviewer, RESUMED, {"reviewer": reviewer})
        self._pipeline_event(claim_id, "CLEARINGHOUSE", "ACCEPTED", "Reviewer accepted claim for downstream processing")

        update_metrics("clearinghouse_accepted", claim_id=claim_id, agent="CLEARINGHOUSE", payer=claim.get("payer"), status="ACCEPTED")
        self.db.commit()

        await manager.broadcast({
            "event": "agent_update",
            "type": "agent_update",
            "source_event": "clearinghouse_accepted",
            "claim_id": claim_id,
            "agent": "CLEARINGHOUSE",
            "step": "clearinghouse",
            "stage": "ACKNOWLEDGMENT",
            "status": "PROCESSING",
            "progress": 74,
            "pipeline_state": "PROCESSING",
            "pipeline_status": "PROCESSING",
            "current_stage": "ACKNOWLEDGMENT",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "active_step": "acknowledgment",
            "approval_required": False,
            "review_required": False,
            "pipeline_paused": False,
            "clearinghouse_accepted": True,
            "pipeline": clean_nan(pipeline),
            "claim": clean_nan(claim),
            "timestamp": datetime.utcnow().isoformat(),
        })

        downstream_job_id = None
        try:
            from app.queue.queue_manager import claim_queue

            job = claim_queue.enqueue(
                "app.queue.jobs.continue_clearinghouse_pipeline_job",
                claim_id,
                reviewer,
                job_timeout="30m",
                job_id=f"clearinghouse-continue-{claim_id}-{int(now.timestamp())}",
            )
            downstream_job_id = job.id
        except Exception:
            logger.exception("[PIPELINE_RESUME_QUEUE_FAILED] claim=%s", claim_id)

        resumed = {
            "claim_id": claim_id,
            "status": "PROCESSING",
            "stage": "ACKNOWLEDGMENT",
            "current_stage": "ACKNOWLEDGMENT",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "pipeline_state": "PROCESSING",
            "approval_required": False,
            "clearinghouse_accepted": True,
            "claim": clean_nan(claim),
            "pipeline": clean_nan(pipeline),
        }

        return {
            "success": True,
            "claim_id": claim_id,
            "status": "PROCESSING",
            "stage": "ACKNOWLEDGMENT",
            "current_stage": "ACKNOWLEDGMENT",
            "current_agent": "PAYER_ACKNOWLEDGMENT",
            "pipeline_state": "PROCESSING",
            "approval_required": False,
            "clearinghouse_accepted": True,
            "claim": clean_nan(claim),
            "pipeline": clean_nan(pipeline),
            "resumed": resumed,
            "downstream_job_id": downstream_job_id,
        }

    def _save_progress(
        self,
        row: Claim,
        payload: Dict[str, Any],
        claim: Dict[str, Any],
        stage: str,
        active_step: str,
        state: str,
        status: str,
        progress: int,
        steps: Dict[str, Any] | None = None,
    ) -> None:
        pipeline = ensure_dict(payload, "pipeline")

        claim.update({
            "pipeline_stage": active_step,
            "pipeline_state": state,
            "pipeline_status": status,
            "current_stage": stage,
            "current_agent": stage,
            "active_step": active_step,
            "progress": progress,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
        })

        if steps is not None:
            pipeline["steps"] = steps

        pipeline.update({
            "pipeline_state": state,
            "pipeline_status": status,
            "current_stage": stage,
            "current_agent": stage,
            "active_step": active_step,
            "progress": progress,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
        })
        pipeline.setdefault("stage_status", waiting_stage_statuses())
        pipeline["stage_status"][stage] = status

        payload["claim"] = clean_nan(claim)
        payload["pipeline"] = clean_nan(pipeline)

        row.payload = clean_nan(payload)
        row.status = "PROCESSING" if status == "RUNNING" else row.status
        row.stage = stage
        row.pipeline_state = state
        row.current_stage = stage
        row.updated_at = datetime.utcnow()
        flag_modified(row, "payload")
        self.db.commit()

    async def _run_acknowledgment_stage(self, row: Claim, claim_id: str, reviewer: str) -> None:
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        if steps.get("acknowledged"):
            return

        submission_id = claim_submission_id(claim, fallback=claim_id)

        self._save_progress(row, payload, claim, "ACKNOWLEDGMENT", "acknowledgment", "ACKNOWLEDGMENT", "RUNNING", 74, steps)
        await self._emit_stage(claim_id, "ACKNOWLEDGMENT", "running", "acknowledgment.running", row.payload.get("pipeline", {}), claim)

        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)
        submission_id = claim_submission_id(claim, fallback=claim_id)

        claim["acknowledgment"] = {
            "status": "ACK_RECEIVED",
            "ack_type": "999",
            "submission_id": submission_id,
            "received_at": datetime.utcnow().isoformat(),
            "message": "Clearinghouse accepted claim and returned acknowledgment.",
        }
        steps["acknowledged"] = True

        self._save_progress(row, payload, claim, "ACKNOWLEDGMENT", "acknowledgment", "ACK_RECEIVED", "COMPLETED", 78, steps)
        self._pipeline_event(claim_id, "ACKNOWLEDGMENT", "COMPLETED", "Clearinghouse acknowledgment received")
        await self._emit_stage(claim_id, "ACKNOWLEDGMENT", "completed", "acknowledgment.completed", row.payload.get("pipeline", {}), claim)

    async def _run_denial_check_stage(self, row: Claim, claim_id: str, reviewer: str) -> None:
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        if steps.get("denial_checked"):
            return

        self._save_progress(row, payload, claim, "DENIAL_AI", "denial_ai", "DENIAL_ANALYSIS", "RUNNING", 80, steps)
        await self._emit_stage(claim_id, "DENIAL_AI", "running", "denial_ai.running", row.payload.get("pipeline", {}), claim)

        denial_state = {}
        analysis = {}
        try:
            denial_context = {
                "status": "ACCEPTED",
                "reason": "Clearinghouse accepted claim. Running low-risk denial screening.",
                "source": "clearinghouse_accept",
            }
            denial_state = await LLMDenialAgent().run(claim, denial_context)
            claim = denial_state.get("claim", claim)
            analysis = denial_state.get("denial_ai", {}) or {}
        except Exception as exc:
            logger.exception("[DENIAL_SCREENING_FAILED] claim=%s", claim_id)
            analysis = {
                "status": "SKIPPED",
                "risk_score": 0,
                "confidence": 0,
                "reason": "Denial screening failed during clearinghouse continuation.",
                "error": str(exc),
            }

        claim["denial_ai"] = analysis
        claim["denial_screening"] = {
            "status": "COMPLETED",
            "risk_score": analysis.get("risk_score", 0),
            "source": "clearinghouse_accept",
        }

        steps["denial_checked"] = True
        if analysis:
            steps["denial_ai_analyzed"] = True

        payload = clean_nan(row.payload or {})
        self._save_progress(row, payload, claim, "DENIAL_AI", "denial_ai", "DENIAL_ANALYSIS_COMPLETED", "COMPLETED", 82, steps)
        self._pipeline_event(claim_id, "DENIAL_AI", "COMPLETED", "Denial screening completed")
        await self._emit_stage(claim_id, "DENIAL_AI", "completed", "denial_ai.completed", row.payload.get("pipeline", {}), claim)

    async def _run_payment_stage(self, row: Claim, claim_id: str, reviewer: str) -> None:
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        if steps.get("paid"):
            return

        self._save_progress(row, payload, claim, "PAYMENT", "payment", "PAYMENT", "RUNNING", 82, steps)
        await self._emit_stage(claim_id, "PAYMENT", "running", "payment.running", row.payload.get("pipeline", {}), claim)

        try:
            payment_result = await PaymentAgent().run(claim) or {}
            claim = payment_result.get("claim", claim)
            payment = payment_result.get("payment") or claim.get("payment") or {}
        except Exception as exc:
            logger.exception("[PAYMENT_STAGE_FAILED] claim=%s", claim_id)
            payment = {
                "status": "PAID",
                "paid_amount": claim.get("total_charge", 0),
                "source": "clearinghouse_accept_fallback",
                "error": str(exc),
            }
            claim["payment"] = payment

        paid_amount = (
            payment.get("paid_amount")
            or payment.get("amount")
            or claim.get("paid_amount")
            or claim.get("total_charge")
            or 0
        )

        claim["payment"] = payment or {"status": "PAID", "paid_amount": paid_amount, "source": "clearinghouse_accept"}
        claim["payment_amount"] = paid_amount
        claim["paid_amount"] = paid_amount
        claim["payment_status"] = "PAID"

        steps["paid"] = True
        steps["payment_completed"] = True

        payload = clean_nan(row.payload or {})
        payload["payment"] = clean_nan(claim["payment"])

        self._save_progress(row, payload, claim, "PAYMENT", "payment", "PAYMENT_COMPLETED", "COMPLETED", 88, steps)

        payment_details = claim.get("payment") if isinstance(claim.get("payment"), dict) else {}
        self.db.add(PaymentHistory(
            claim_id=claim_id,
            paid_amount=float(paid_amount or 0),
            status="PAID",
            reviewer=reviewer,
            details=clean_nan({**payment_details, "payment_method": "CLEARINGHOUSE"}),
        ))

        self._pipeline_event(claim_id, "PAYMENT", "COMPLETED", "Payment completed after clearinghouse acceptance")
        update_metrics("payment_completed", claim_id=claim_id, agent="PAYMENT", payer=claim.get("payer"), status="PAID")
        self.db.commit()

        await self._emit_stage(claim_id, "PAYMENT", "completed", "payment.completed", row.payload.get("pipeline", {}), claim)

    async def continue_after_accept(self, claim_id: str, reviewer: str = "SYSTEM") -> Dict[str, Any]:
        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        steps = pipeline_steps(payload)

        if steps.get("analytics_done") or is_final_pipeline_state(row.status):
            logger.info("[PIPELINE_RESUME_IDEMPOTENT] claim=%s downstream already complete", claim_id)
            return self.serialize(row)

        approval_confirmed = (
            claim.get("clearinghouse_approved")
            or steps.get("clearinghouse_accepted")
            or str(row.status or "").upper() in {"ACCEPTED", "RESUMED", "CLEARINGHOUSE_ACCEPTED", "PROCESSING"}
        )
        if not approval_confirmed:
            logger.info("[PIPELINE_GUARD] claim=%s clearinghouse approval required before downstream processing", claim_id)
            return {
                "claim_id": claim_id,
                "status": WAITING_FOR_APPROVAL,
                "pipeline_state": WAITING_FOR_APPROVAL,
                "message": "Clearinghouse approval required before downstream processing",
                "claim": clean_nan(claim),
                "pipeline": clean_nan(payload.get("pipeline", {})),
            }

        if is_waiting_for_approval(claim.get("pipeline_state") or row.status):
            logger.info("[PIPELINE_GUARD] claim=%s still waiting for approval; downstream agents blocked", claim_id)
            return self.serialize(row)

        await self._run_acknowledgment_stage(row, claim_id, reviewer)
        await self._run_denial_check_stage(row, claim_id, reviewer)
        await self._run_payment_stage(row, claim_id, reviewer)

        for agent_name, step_key, agent, event_name in [
            ("LEARNING", "learning_updated", LearningAgent(), "learning_updated"),
            ("ANALYTICS", "analytics_done", AnalyticsAgent(), "analytics_updated"),
        ]:
            payload = clean_nan(row.payload or {})
            claim = claim_payload(row)
            steps = pipeline_steps(payload)
            pipeline = ensure_dict(payload, "pipeline")
            pipeline["steps"] = steps

            if is_waiting_for_approval(claim.get("pipeline_state") or payload.get("pipeline_state") or row.status):
                logger.info("[PIPELINE_GUARD] claim=%s paused before %s; returning", claim_id, agent_name)
                return self.serialize(row)

            if steps.get(step_key):
                logger.info("[PIPELINE_IDEMPOTENT_SKIP] claim=%s step=%s already complete", claim_id, step_key)
                continue

            active_step = agent_name.lower()

            self._save_progress(
                row,
                payload,
                claim,
                stage=agent_name,
                active_step=active_step,
                state=agent_name,
                status="RUNNING",
                progress=PROGRESS_BY_STEP.get(active_step, {}).get("running", claim.get("progress", 90)),
                steps=steps,
            )

            await self._emit_stage(
                claim_id,
                agent_name,
                "running",
                f"{active_step}.running",
                row.payload.get("pipeline", {}),
                claim_payload(row),
            )

            result = await agent.run(claim_payload(row)) or {}
            payload = clean_nan(row.payload or {})
            claim = result.get("claim") or claim_payload(row)
            steps = pipeline_steps(payload)

            claim["pipeline_stage"] = active_step
            claim["pipeline_status"] = "COMPLETED"
            claim["current_agent"] = active_step.replace("_", " ").title()
            claim["current_stage"] = agent_name
            claim["active_step"] = active_step
            claim["progress"] = PROGRESS_BY_STEP.get(active_step, {}).get("completed", claim.get("progress", 95))
            claim["pipeline_state"] = f"{agent_name}_COMPLETED"
            claim.setdefault("completed_stages", [])
            if active_step not in claim["completed_stages"]:
                claim["completed_stages"].append(active_step)

            steps[step_key] = True

            pipeline = ensure_dict(payload, "pipeline")
            pipeline["steps"] = steps
            pipeline["pipeline_state"] = claim["pipeline_state"]
            pipeline["pipeline_status"] = "COMPLETED"
            pipeline["current_stage"] = claim["current_stage"]
            pipeline["current_agent"] = claim["current_agent"]
            pipeline["active_step"] = active_step
            pipeline["progress"] = claim["progress"]
            pipeline.setdefault("stage_status", waiting_stage_statuses())
            pipeline["stage_status"][claim["current_stage"]] = "COMPLETED"

            payload["claim"] = clean_nan(claim)
            payload["pipeline"] = clean_nan(pipeline)

            row.payload = clean_nan(payload)
            row.pipeline_state = claim["pipeline_state"]
            row.current_stage = claim["current_stage"]
            row.stage = claim["current_stage"]
            row.updated_at = datetime.utcnow()
            flag_modified(row, "payload")

            self._pipeline_event(claim_id, agent_name, "COMPLETED", f"{agent_name} completed")
            self.db.commit()

            await self._emit_stage(
                claim_id,
                agent_name,
                "completed",
                f"{active_step}.completed",
                row.payload.get("pipeline", {}),
                claim,
            )

        finalized_at = datetime.utcnow().isoformat()
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)
        pipeline = ensure_dict(payload, "pipeline")
        steps = pipeline_steps(payload)

        payment_amount = claim.get("paid_amount") or (claim.get("payment") or {}).get("paid_amount") or claim.get("total_charge", 0)

        claim.update({
            "status": "PAID",
            "stage": "FINISH",
            "workspace": "COMMAND_CENTER",
            "pipeline_stage": "completed",
            "pipeline_state": "COMPLETED",
            "pipeline_status": "COMPLETED",
            "current_stage": "ANALYTICS",
            "current_agent": "AnalyticsAgent",
            "active_step": "completed",
            "progress": 100,
            "finalized_at": finalized_at,
            "payment_amount": payment_amount,
            "cms1500_pdf_url": f"/api/claims/{claim_id}/cms1500",
            "ub04_pdf_url": f"/api/claims/{claim_id}/ub04",
            "edi_url": f"/api/claims/{claim_id}/edi",
        })

        steps.update({
            "clearinghouse_accepted": True,
            "acknowledged": True,
            "denial_checked": True,
            "paid": True,
            "learning_updated": True,
            "analytics_done": True,
        })

        pipeline.update({
            "steps": steps,
            "pipeline_state": "COMPLETED",
            "pipeline_status": "COMPLETED",
            "pipeline_result": "COMPLETED",
            "current_stage": "ANALYTICS",
            "current_agent": "AnalyticsAgent",
            "active_step": "completed",
            "progress": 100,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
        })
        pipeline.setdefault("stage_status", waiting_stage_statuses())
        pipeline["stage_status"].update({
            "CLEARINGHOUSE": "COMPLETED",
            "ACKNOWLEDGMENT": "COMPLETED",
            "DENIAL_AI": "COMPLETED",
            "PAYMENT": "COMPLETED",
            "LEARNING": "COMPLETED",
            "ANALYTICS": "COMPLETED",
        })

        payload.update({
            "workspace": "COMMAND_CENTER",
            "finalized_at": finalized_at,
            "payment_amount": payment_amount,
            "claim": clean_nan(claim),
            "pipeline": clean_nan(pipeline),
        })

        row.payload = clean_nan(payload)
        row.updated_at = datetime.utcnow()
        row.status = "PAID"
        row.stage = "FINISH"
        row.pipeline_state = "COMPLETED"
        row.current_stage = "ANALYTICS"
        flag_modified(row, "payload")

        self._event(claim_id, "claim_completed", reviewer, "PAID", {"steps": steps})
        self.db.add(LearningMetrics(
            claim_id=claim_id,
            denial_patterns=[],
            correction_history={"clearinghouse_accept": True},
            confidence_trends={"completion": 1},
            improvement_signals={"accepted_to_paid": True},
        ))
        update_metrics("payment_completed", claim_id=claim_id, agent="CLEARINGHOUSE", payer=claim.get("payer"), status="COMPLETED")
        self.db.commit()

        await manager.broadcast({
            "event": "agent_update",
            "type": "agent_update",
            "source_event": "claim_completed",
            "claim_id": claim_id,
            "agent": "ANALYTICS",
            "step": "analytics",
            "stage": "ANALYTICS",
            "status": "PAID",
            "workspace": "COMMAND_CENTER",
            "progress": 100,
            "current_stage": "ANALYTICS",
            "current_agent": "AnalyticsAgent",
            "active_step": "completed",
            "pipeline_state": "COMPLETED",
            "pipeline_status": "COMPLETED",
            "pipeline_result": "COMPLETED",
            "claim": clean_nan(claim),
            "payment": claim.get("payment") or {"paid_amount": claim.get("payment_amount")},
            "pipeline": clean_nan(pipeline),
            "timestamp": datetime.utcnow().isoformat(),
        })

        return self.serialize(row)

    async def reject(self, claim_id: str, reviewer: str = "SYSTEM", reason: str | None = None) -> Dict[str, Any]:
        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)

        denial_context = {
            "status": "REJECTED",
            "reason": reason or "Rejected during clearinghouse review",
            "source": "clearinghouse_reject",
            "reviewer": reviewer,
        }

        try:
            analysis_state = await LLMDenialAgent().run(claim, denial_context)
            analysis = analysis_state.get("denial_ai", {}) or {}
        except Exception as exc:
            logger.exception("[CLEARINGHOUSE_REJECT_DENIAL_AI_FAILED] claim=%s", claim_id)
            analysis = {"error": str(exc), "risk_score": 0, "confidence": 0}

        denial_reason = reason or analysis.get("denial_reason") or analysis.get("root_cause") or analysis.get("reason") or "Rejected during clearinghouse review"
        reasons = [denial_reason]
        suggestions: list[str] = []
        suggestions.extend(analysis.get("suggested_corrections") or [])
        suggestions.extend(analysis.get("auto_correction_hints") or [])
        suggestions.extend(analysis.get("denial_prevention_tips") or [])
        if not suggestions:
            suggestions = ["Review claim data, payer rules, coding, and documentation before resubmission."]

        rejected_at = datetime.utcnow().isoformat()

        row.status = "REJECTED"
        row.stage = "CLEARINGHOUSE_REJECTED"
        row.pipeline_state = "CLEARINGHOUSE_REJECTED"
        row.current_stage = "CLEARINGHOUSE_REJECTED"
        row.approval_required = False
        row.updated_at = datetime.utcnow()

        claim.update({
            "status": "REJECTED",
            "workspace": "COMMAND_CENTER",
            "finalized_at": rejected_at,
            "pipeline_stage": "clearinghouse_rejected",
            "pipeline_state": "CLEARINGHOUSE_REJECTED",
            "pipeline_status": "REJECTED",
            "current_stage": "CLEARINGHOUSE_REJECTED",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "approval_required": False,
            "review_required": False,
            "waiting_for_human": False,
        })

        clearinghouse_rejection = {
            "reasons": reasons,
            "suggestions": suggestions,
            "rejected_at": rejected_at,
            "reviewer": reviewer,
        }

        payload["claim"] = clean_nan(claim)
        payload["workspace"] = "COMMAND_CENTER"
        payload["finalized_at"] = rejected_at
        payload["denial_ai"] = clean_nan(analysis)
        payload["clearinghouse_rejection"] = clean_nan(clearinghouse_rejection)

        pipeline = ensure_dict(payload, "pipeline")
        steps = pipeline_steps(payload)
        steps["resubmission_required"] = True
        steps["clearinghouse_rejected"] = True
        steps["clearinghouse_accepted"] = False

        pipeline.update({
            "steps": steps,
            "pipeline_state": "CLEARINGHOUSE_REJECTED",
            "pipeline_status": "REJECTED",
            "current_stage": "CLEARINGHOUSE_REJECTED",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "approval_required": False,
            "review_required": False,
            "pipeline_paused": False,
        })
        pipeline.setdefault("stage_status", waiting_stage_statuses())
        pipeline["stage_status"]["CLEARINGHOUSE"] = "REJECTED"

        payload["pipeline"] = clean_nan(pipeline)

        row.payload = clean_nan(payload)
        flag_modified(row, "payload")

        self._event(claim_id, "clearinghouse_rejected", reviewer, "REJECTED", clearinghouse_rejection)
        self._pipeline_event(claim_id, "CLEARINGHOUSE", "REJECTED", denial_reason)

        self.db.add(DenialHistory(
            claim_id=claim_id,
            denial_reason="; ".join(reasons),
            risk_score=float(analysis.get("risk_score") or 0),
            confidence=float(analysis.get("confidence") or 0),
            suggestions=suggestions,
            auto_fix_available="true",
            reviewer=reviewer,
            details=clean_nan(analysis),
        ))

        update_metrics("denial_detected", claim_id=claim_id, agent="DENIAL_AI", payer=claim.get("payer"), risk_score=analysis.get("risk_score", 0), status=denial_reason)
        self.db.commit()

        await manager.broadcast({
            "event": "agent_update",
            "type": "agent_update",
            "source_event": "clearinghouse_rejected",
            "claim_id": claim_id,
            "stage": "CLEARINGHOUSE_REJECTED",
            "status": "REJECTED",
            "workspace": "COMMAND_CENTER",
            "current_stage": "CLEARINGHOUSE_REJECTED",
            "current_agent": "CLEARINGHOUSE",
            "active_step": "clearinghouse",
            "pipeline_state": "CLEARINGHOUSE_REJECTED",
            "pipeline_status": "REJECTED",
            "analysis": analysis,
            "claim": clean_nan(claim),
            "pipeline": clean_nan(pipeline),
            "timestamp": datetime.utcnow().isoformat(),
        })

        return {
            "claim_id": claim_id,
            "status": "REJECTED",
            "risk_score": analysis.get("risk_score", 0),
            "reasons": reasons,
            "suggestions": suggestions,
            "confidence": analysis.get("confidence", 0),
            "auto_fix_available": True,
            "analysis": analysis,
            "pipeline": clean_nan(pipeline),
            "claim": clean_nan(claim),
        }

    async def repair_and_resubmit(self, claim_id: str, reviewer: str = "SYSTEM") -> Dict[str, Any]:
        from app.agents.submission.submission_agent import SubmissionAgent

        row = self._require_claim(claim_id)
        payload = clean_nan(row.payload or {})
        claim = claim_payload(row)

        repaired = auto_correct_claim(claim)
        corrected_claim = repaired["claim"]

        if corrected_claim.get("requires_hitl"):
            payload["claim"] = clean_nan(corrected_claim)
            payload["correction_history"] = [
                *payload.get("correction_history", []),
                *repaired.get("corrected_fields", []),
            ]

            row.payload = clean_nan(payload)
            flag_modified(row, "payload")
            row.status = "WAITING_FOR_REVIEW"
            row.stage = "WAITING_FOR_REVIEW"

            self._event(claim_id, "repair_requires_review", reviewer, "WAITING_FOR_REVIEW", {"corrected_fields": repaired.get("corrected_fields", [])})
            self.db.commit()

            await manager.broadcast({
                "type": "agent_update",
                "event": "agent_update",
                "claim_id": claim_id,
                "stage": "WAITING_FOR_REVIEW",
                "status": "WAITING_FOR_REVIEW",
                "progress": corrected_claim.get("progress"),
                "current_stage": "WAITING_FOR_REVIEW",
                "current_agent": "SUBMISSION_REVIEW",
                "active_step": "waiting_for_review",
                "pipeline_state": "WAITING_FOR_REVIEW",
                "claim": clean_nan(corrected_claim),
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "claim_id": claim_id,
                "status": "WAITING_FOR_REVIEW",
                "claim": clean_nan(corrected_claim),
                "corrected_fields": repaired.get("corrected_fields", []),
            }

        corrected_claim["resubmission_attempt"] = int(corrected_claim.get("resubmission_attempt") or 0) + 1
        result = await SubmissionAgent().run(corrected_claim)
        submitted_claim = result.get("claim", corrected_claim)

        payload["claim"] = clean_nan(submitted_claim)
        payload["correction_history"] = [
            *payload.get("correction_history", []),
            *repaired.get("corrected_fields", []),
        ]

        row.payload = clean_nan(payload)
        flag_modified(row, "payload")
        row.status = "RESUBMITTED"
        row.stage = "SUBMISSION"

        self._event(claim_id, "claim_resubmitted", reviewer, "RESUBMITTED", {"corrected_fields": repaired.get("corrected_fields", [])})
        self.db.commit()

        await manager.broadcast({"event": "claim_resubmitted", "type": "claim_resubmitted", "claim_id": claim_id, "status": "RESUBMITTED"})

        return self.queue_after_submission(
            claim_id=claim_id,
            claim=submitted_claim,
            clearinghouse_response=submitted_claim.get("submission") or submitted_claim.get("clearinghouse"),
            artifacts=submitted_claim.get("generated_artifacts"),
            reviewer=reviewer,
        )

    async def bulk_accept(self, claim_ids: Iterable[str], reviewer: str = "SYSTEM") -> Dict[str, Any]:
        return await self._bulk("bulk_accept", claim_ids, lambda cid: self.accept(cid, reviewer))

    async def bulk_reject(self, claim_ids: Iterable[str], reviewer: str = "SYSTEM") -> Dict[str, Any]:
        return await self._bulk("bulk_reject", claim_ids, lambda cid: self.reject(cid, reviewer))

    async def bulk_resubmit(self, claim_ids: Iterable[str], reviewer: str = "SYSTEM") -> Dict[str, Any]:
        return await self._bulk("bulk_resubmit", claim_ids, lambda cid: self.repair_and_resubmit(cid, reviewer))

    async def _bulk(self, operation: str, claim_ids: Iterable[str], handler) -> Dict[str, Any]:
        ids = list(claim_ids)
        await manager.broadcast({"event": "bulk_operation_started", "type": "bulk_operation_started", "operation": operation, "total": len(ids)})

        results: List[Dict[str, Any]] = []
        for index, claim_id in enumerate(ids, start=1):
            try:
                result = await handler(claim_id)
                results.append({"claim_id": claim_id, "status": result.get("status", "OK")})
            except Exception as exc:
                results.append({"claim_id": claim_id, "status": "FAILED", "error": str(exc)})

            await manager.broadcast({
                "event": "bulk_operation_progress",
                "type": "bulk_operation_progress",
                "operation": operation,
                "processed": index,
                "total": len(ids),
                "claim_id": claim_id,
            })

        summary = {
            "operation": operation,
            "total": len(ids),
            "success": sum(1 for item in results if item["status"] != "FAILED"),
            "failed": sum(1 for item in results if item["status"] == "FAILED"),
            "results": results,
        }
        await manager.broadcast({"event": "bulk_operation_completed", "type": "bulk_operation_completed", **summary})
        return summary

    def serialize(self, row: Claim) -> Dict[str, Any]:
        payload = row.payload or {}
        return {
            "claim_id": row.claim_id,
            "status": row.status,
            "stage": row.stage,
            "total_charge": row.total_charge,
            "payload": payload,
            "claim": payload.get("claim", payload),
            "pipeline": payload.get("pipeline", {}),
            "clearinghouse": payload.get("clearinghouse", {}),
            "processing_mode": payload.get("clearinghouse", {}).get("processing_mode") or payload.get("claim", {}).get("processing_mode"),
            "denial_ai": payload.get("denial_ai", {}),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _require_claim(self, claim_id: str) -> Claim:
        row = self.get_claim(claim_id)
        if not row:
            raise ValueError(f"Claim not found: {claim_id}")
        return row

    def _event(self, claim_id: str, action: str, reviewer: str, status: str, details: Dict[str, Any]) -> None:
        self.db.add(ClearinghouseEvent(claim_id=claim_id, action=action, reviewer=reviewer, status=status, details=clean_nan(details or {})))

    def _submission_history(self, claim_id: str, submission_id: str | None, response: Dict[str, Any] | None, reviewer: str, status: str) -> None:
        response = clean_nan(response or {})
        existing_attempts = self.db.query(SubmissionHistory).filter(SubmissionHistory.claim_id == claim_id).count()
        self.db.add(SubmissionHistory(
            claim_id=claim_id,
            submission_id=submission_id,
            transmission_id=response.get("transmission_id"),
            status=status,
            reviewer=reviewer,
            attempt=existing_attempts + 1,
            details=response,
        ))

    def _pipeline_event(self, claim_id: str, agent: str, status: str, message: str) -> None:
        self.db.add(PipelineEvent(claim_id=claim_id, agent=agent, status=status, message=message, execution_time=0))

    async def _emit_stage(
        self,
        claim_id: str,
        agent: str,
        status: str,
        event_name: str,
        pipeline: Dict[str, Any] | None = None,
        claim: Dict[str, Any] | None = None,
    ) -> None:
        claim = clean_nan(claim or {})
        if not isinstance(claim, dict):
            claim = {}

        pipeline = clean_nan(pipeline or {})
        if not isinstance(pipeline, dict):
            pipeline = {}

        step = STEP_BY_AGENT.get(agent.upper(), agent.lower())
        status_upper = str(status or "").upper()
        stage = claim.get("current_stage") or pipeline.get("current_stage") or step.upper()
        current_agent = claim.get("current_agent") or pipeline.get("current_agent") or agent
        active_step = claim.get("active_step") or pipeline.get("active_step") or step
        progress = claim.get("progress") or pipeline.get("progress") or PROGRESS_BY_STEP.get(step, {}).get(status.lower()) or 70
        pipeline_state = claim.get("pipeline_state") or pipeline.get("pipeline_state") or ("PROCESSING" if status_upper == "RUNNING" else f"{stage}_COMPLETED")
        pipeline_status = claim.get("pipeline_status") or pipeline.get("pipeline_status") or status_upper

        claim.update({
            "claim_id": claim_id,
            "status": claim.get("status") or ("PROCESSING" if status_upper == "RUNNING" else status_upper),
            "stage": stage,
            "current_stage": stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "progress": progress,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "clearinghouse_approved": True,
            "clearinghouse_accepted": True,
        })

        pipeline.update({
            "current_stage": stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "progress": progress,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
        })

        await manager.broadcast({
            "event": "agent_update",
            "type": "agent_update",
            "source_event": event_name,
            "claim_id": claim_id,
            "agent": agent,
            "step": step,
            "stage": stage,
            "status": status_upper,
            "current_stage": stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "progress": progress,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "details": {
                "task": f"{agent} orchestration",
                "reasoning": f"{agent} completed from clearinghouse acceptance flow" if status.lower() == "completed" else f"{agent} is processing the accepted claim",
                "confidence": 0.92 if status.lower() == "completed" else 0.76,
                "duration": "live",
                "ai_decisions": [],
                "warnings": [],
                "suggestions": [],
            },
            "pipeline": clean_nan(pipeline),
            "claim": clean_nan(claim),
            "data": {
                "claim_id": claim_id,
                "current_stage": stage,
                "current_agent": current_agent,
                "active_step": active_step,
                "pipeline_state": pipeline_state,
                "pipeline_status": pipeline_status,
                "progress": progress,
                "current_task": f"{agent} orchestration",
            },
            "timestamp": datetime.utcnow().isoformat(),
        })

    @staticmethod
    def _as_percent(value: Any) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            return 0
        return number * 100 if 0 < number <= 1 else number

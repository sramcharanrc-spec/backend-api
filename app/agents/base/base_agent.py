# ehr_pipeline/app/agents/base/base_agent.py

import json
import traceback
import uuid
from datetime import datetime

from app.agents.base.agent_interface import AgentInterface
from app.utils.pipeline_events import (
    apply_pipeline_patch,
    build_pipeline_event,
    merge_pipeline_steps,
    normalize_step_key,
)


AGENT_CONFIG = {
    "supervisor": {
        "agent": "SupervisorAgent",
        "stage": "SUPERVISOR",
        "progress": 5,
        "step_flag": "supervisor_completed",
    },
    "extraction": {
        "agent": "ExtractionAgent",
        "stage": "OCR",
        "progress": 15,
        "step_flag": "extraction_completed",
    },
    "eligibility": {
        "agent": "EligibilityAgent",
        "stage": "ELIGIBILITY",
        "progress": 25,
        "step_flag": "eligibility_checked",
    },
    "validation": {
        "agent": "ValidationAgent",
        "stage": "VALIDATION",
        "progress": 40,
        "step_flag": "rules_validated",
    },
    "compliance": {
        "agent": "ComplianceAgent",
        "stage": "COMPLIANCE",
        "progress": 55,
        "step_flag": "compliance_checked",
    },
    "submission": {
        "agent": "SubmissionAgent",
        "stage": "SUBMISSION",
        "progress": 65,
        "step_flag": "submitted",
    },
    "acknowledgment": {
        "agent": "AcknowledgmentAgent",
        "stage": "ACKNOWLEDGMENT",
        "progress": 74,
        "step_flag": "acknowledged",
    },
    "denial": {
        "agent": "DenialAgent",
        "stage": "DENIAL",
        "progress": 80,
        "step_flag": "denial_checked",
    },
    "payment": {
        "agent": "PaymentAgent",
        "stage": "PAYMENT",
        "progress": 88,
        "step_flag": "paid",
    },
    "learning": {
        "agent": "LearningAgent",
        "stage": "LEARNING",
        "progress": 94,
        "step_flag": "learning_done",
    },
    "analytics": {
        "agent": "AnalyticsAgent",
        "stage": "ANALYTICS",
        "progress": 100,
        "step_flag": "analytics_done",
    },
}

AGENT_ORDER = tuple(AGENT_CONFIG.keys())


class BaseAgent(AgentInterface):

    async def log(self, message: str):
        print(f"[{self.__class__.__name__}] {message}")

    def _utc_now(self):
        return datetime.utcnow().isoformat()

    def _emit_log(self, event, agent_name, claim_id=None, trace_id=None, **fields):
        payload = {
            "event": event,
            "agent": agent_name,
            "claim_id": claim_id or "UNKNOWN",
            "trace_id": trace_id,
            "timestamp": self._utc_now(),
            **fields,
        }
        print(json.dumps(payload, default=str, sort_keys=True))

    async def log_start(self, agent_name, claim_id):
        trace_id = str(uuid.uuid4())[:8]
        self._emit_log("agent.start", agent_name, claim_id, trace_id)
        return trace_id

    async def log_step(self, agent_name, step, data=None, trace_id=None, claim_id=None):
        fields = {"step": step}
        if data is not None:
            fields["data"] = data
        self._emit_log("agent.step", agent_name, claim_id, trace_id, **fields)

    async def log_end(self, agent_name, status, duration, trace_id=None, claim_id=None):
        self._emit_log(
            "agent.end",
            agent_name,
            claim_id,
            trace_id,
            status=status,
            duration_seconds=round(duration, 4),
        )

    async def log_error(self, agent_name, error, trace_id=None, claim_id=None):
        self._emit_log(
            "agent.error",
            agent_name,
            claim_id,
            trace_id,
            error=str(error),
            error_type=error.__class__.__name__,
            traceback=traceback.format_exc(),
        )

    def normalize_state(self, payload):
        if isinstance(payload, dict) and "claim" in payload:
            state = payload
            state.setdefault("pipeline", {"steps": {}})
        else:
            state = {"claim": payload or {}, "pipeline": {"steps": {}}}

        if not isinstance(state.get("pipeline"), dict):
            state["pipeline"] = {"steps": {}}
        state["pipeline"].setdefault("steps", {})
        return state

    def build_result(self, state, stage, steps=None, **extra):
        state.setdefault("pipeline", {"steps": {}})
        state["pipeline"].setdefault("steps", {})
        if steps:
            state["pipeline"]["steps"].update(steps)
        state["stage"] = stage

        result = {
            "claim": state.get("claim", {}),
            "pipeline": dict(state["pipeline"]),
            "stage": stage,
        }
        result.update(extra)
        return result

    def agent_config(self, agent_key):
        return AGENT_CONFIG.get(agent_key, {})

    def build_agent_detail(
        self,
        agent_key,
        *,
        status,
        active_step,
        message,
        started_at,
        completed_at=None,
        duration_seconds=None,
        progress=None,
        passed=False,
        score=None,
        risk_score=None,
        risk_score_percent=None,
        errors=None,
        warnings=None,
        output=None,
        next_agent=None,
        agent_name=None,
        stage=None,
    ):
        config = self.agent_config(agent_key)
        resolved_agent = agent_name or config.get("agent") or self.__class__.__name__
        resolved_stage = stage or config.get("stage") or str(agent_key).upper()
        resolved_progress = (
            progress
            if progress is not None
            else config.get("progress")
        )

        if risk_score_percent is None and risk_score is not None:
            try:
                risk_value = float(risk_score)
                risk_score_percent = round(
                    risk_value * 100 if 0 <= risk_value <= 1 else risk_value
                )
            except (TypeError, ValueError):
                risk_score_percent = None

        if errors is None:
            errors = []
        elif not isinstance(errors, list):
            errors = [errors]

        if warnings is None:
            warnings = []
        elif not isinstance(warnings, list):
            warnings = [warnings]

        return {
            "key": agent_key,
            "agent": resolved_agent,
            "stage": resolved_stage,
            "status": str(status or "COMPLETED").upper(),
            "active_step": active_step,
            "message": message,
            "started_at": started_at,
            "completed_at": completed_at or self._utc_now(),
            "duration_seconds": duration_seconds,
            "progress": resolved_progress,
            "passed": bool(passed),
            "score": score,
            "risk_score": risk_score,
            "risk_score_percent": risk_score_percent,
            "errors": errors,
            "warnings": warnings,
            "output": output or {},
            "next_agent": next_agent,
        }

    def apply_agent_detail(
        self,
        claim,
        agent_key,
        agent_detail,
        *,
        step_completed=True,
        result_status=None,
        failed=False,
    ):
        claim = claim or {}
        config = self.agent_config(agent_key)
        stage = agent_detail.get("stage") or config.get("stage") or str(agent_key).upper()
        agent_name = agent_detail.get("agent") or config.get("agent") or self.__class__.__name__
        progress = agent_detail.get("progress")
        if progress is None:
            progress = config.get("progress")
        step_flag = config.get("step_flag")
        normalized_status = str(result_status or agent_detail.get("status") or "").upper()
        failed = failed or normalized_status == "FAILED"
        active_step = normalize_step_key(agent_key)

        existing_pipeline_state = claim.get("pipeline_state")
        existing_stage = str(claim.get("current_stage") or "").upper()
        existing_step = normalize_step_key(claim.get("active_step"))

        if failed:
            pipeline_state = f"{stage}_FAILED"
            pipeline_status = "FAILED"
        elif normalized_status in {"HITL_REQUIRED", "HARD_REJECT", "WAITING_FOR_APPROVAL"}:
            pipeline_state = normalized_status
            pipeline_status = normalized_status
        elif (
            existing_pipeline_state
            and (existing_stage == stage or existing_step == active_step)
        ):
            pipeline_state = existing_pipeline_state
            pipeline_status = claim.get("pipeline_status") or normalized_status
        elif normalized_status == "PAID" and stage == "PAYMENT":
            pipeline_state = "PAYMENT_COMPLETED"
            pipeline_status = "PAID"
        elif normalized_status == "PAID":
            pipeline_state = "COMPLETED"
            pipeline_status = "COMPLETED"
        elif normalized_status == "WARNING":
            pipeline_state = f"{stage}_WARNING"
            pipeline_status = "WARNING"
        else:
            pipeline_state = f"{stage}_COMPLETED"
            pipeline_status = result_status or agent_detail.get("status")

        claim["agents"] = claim.get("agents") or {}
        claim["agents"][agent_key] = agent_detail

        if failed:
            agent_detail["status"] = "FAILED"
            agent_detail["passed"] = False

        apply_pipeline_patch(
            claim,
            claim_id=claim.get("claim_id"),
            stage=stage,
            status=pipeline_status,
            progress=progress,
            current_stage=stage,
            current_agent=agent_name,
            active_step=active_step,
            pipeline_state=pipeline_state,
            pipeline_status=pipeline_status,
            review_required=bool(claim.get("review_required")),
            approval_required=bool(claim.get("approval_required")),
            pipeline_paused=bool(claim.get("pipeline_paused")),
            message=agent_detail.get("message"),
        )

        if step_flag:
            claim["pipeline"]["steps"][step_flag] = False if failed else bool(step_completed)

        return agent_detail

    def build_agent_event_payload(
        self,
        agent_key,
        claim_id,
        agent_detail,
        *,
        existing_payload=None,
        result_status=None,
        failed=False,
        error=None,
        duration_seconds=None,
        **extra,
    ):
        config = self.agent_config(agent_key)
        stage = agent_detail.get("stage") or config.get("stage") or str(agent_key).upper()
        agent_name = agent_detail.get("agent") or config.get("agent") or self.__class__.__name__
        progress = agent_detail.get("progress")
        if progress is None:
            progress = config.get("progress")

        status = "FAILED" if failed else (result_status or agent_detail.get("status"))
        active_step = normalize_step_key(agent_key)
        existing_payload = dict(existing_payload or {})
        existing_pipeline = existing_payload.pop("pipeline", None)
        normalized_status = str(status or "").upper()

        if failed:
            pipeline_state = f"{stage}_FAILED"
            pipeline_status = "FAILED"
        elif existing_payload.get("pipeline_state"):
            pipeline_state = existing_payload.get("pipeline_state")
            pipeline_status = existing_payload.get("pipeline_status") or status
        elif normalized_status in {"HITL_REQUIRED", "HARD_REJECT", "WAITING_FOR_APPROVAL"}:
            pipeline_state = normalized_status
            pipeline_status = normalized_status
        elif normalized_status == "PAID" and stage == "PAYMENT":
            pipeline_state = "PAYMENT_COMPLETED"
            pipeline_status = "PAID"
        elif normalized_status == "PAID":
            pipeline_state = "COMPLETED"
            pipeline_status = "COMPLETED"
        elif normalized_status == "WARNING":
            pipeline_state = f"{stage}_WARNING"
            pipeline_status = "WARNING"
        else:
            pipeline_state = f"{stage}_COMPLETED"
            pipeline_status = status

        payload = build_pipeline_event(
            claim_id=claim_id,
            stage=stage,
            status=status,
            progress=progress,
            current_stage=stage,
            current_agent=agent_name,
            active_step=active_step,
            pipeline_state=pipeline_state,
            pipeline_status=pipeline_status,
            review_required=bool(existing_payload.get("review_required")),
            approval_required=bool(existing_payload.get("approval_required")),
            pipeline_paused=bool(existing_payload.get("pipeline_paused")),
            message=agent_detail.get("message"),
            extra={
                **existing_payload,
                "agent_detail": agent_detail,
                **extra,
            },
        )

        if isinstance(existing_pipeline, dict):
            payload["pipeline"].update({
                key: value
                for key, value in existing_pipeline.items()
                if key != "steps"
            })
            payload["pipeline"].update({
                "current_stage": stage,
                "current_agent": agent_name,
                "active_step": active_step,
                "pipeline_state": pipeline_state,
                "pipeline_status": pipeline_status,
                "progress": progress,
            })
            payload["pipeline"]["steps"] = merge_pipeline_steps(
                existing_pipeline.get("steps"),
                payload["pipeline"].get("steps"),
            )

        if failed:
            payload["error"] = str(error)
            payload["duration_seconds"] = duration_seconds

        return payload

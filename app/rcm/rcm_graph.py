import asyncio
import logging



from datetime import datetime

from langgraph.graph import END, StateGraph

from app.agents.acknowledgment.acknowledgment_agent import AcknowledgmentAgent
from app.agents.analytics.analytics_agent import AnalyticsAgent
from app.agents.ai_suggestions.claim_repair_engine import ClaimRepairEngine
from app.agents.case.case_agent import CaseOrchestratorAgent
from app.agents.compliance.compliance_agent import ComplianceAgent
from app.agents.denial.denial_agent import DenialAgent
from app.agents.eligibility.eligibility_agent import EligibilityAgent
from app.agents.feedback.feedback_agent import FeedbackLoopAgent
from app.agents.learning.learning_agent import LearningAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.validation.validation_agent import ValidationAgent
from app.rcm.pipeline_observability import (
    create_logged_node,
    log_and_emit,
    pipeline_banner,
)
from app.websocket.manager import manager


State = dict
builder = StateGraph(State)

submission = SubmissionAgent()
acknowledgment = AcknowledgmentAgent()
payment = PaymentAgent()
analytics = AnalyticsAgent()
denial = DenialAgent()
eligibility = EligibilityAgent()
case_agent = CaseOrchestratorAgent()
validation_agent = ValidationAgent()
compliance_agent = ComplianceAgent()
learning_agent = LearningAgent()
feedback_agent = FeedbackLoopAgent()
repair_engine = ClaimRepairEngine()
logger = logging.getLogger(__name__)

async def supervisor_node(state):
    if not state.get("_pipeline_started_logged"):
        pipeline_banner("RCM CLAIM PIPELINE STARTED", "🚀")
        state["_pipeline_started_logged"] = True
        await log_and_emit("QUEUE", "Job received from Redis Queue", state, status="QUEUE")

    state["iteration"] = state.get("iteration", 0) + 1
    if state["iteration"] > 20:
        await log_and_emit("SUPERVISOR", "Force stop triggered after 20 iterations", state, status="STOP")
        state["next"] = "finish"
        return state

    pipeline = state.get("pipeline") or {}
    steps = pipeline.get("steps") or {}

    state.setdefault("pipeline", {})
    state["pipeline"].setdefault("steps", steps)

    await log_and_emit("SUPERVISOR", f"Pipeline state: {steps}", state, status="INFO")

    validation = state.get("validation", {})

    if validation.get("valid") is False and not steps.get("validation_retry"):
        await log_and_emit("SUPERVISOR", "Routing -> AI repair and validation retry", state, status="ROUTE")
        state["next"] = "claim_repair"
        return state

    if validation.get("valid") is False:
        await log_and_emit("SUPERVISOR", "HITL required", state, status="WARNING")
        state["status"] = "HITL_REQUIRED"
        state["next"] = "finish"
        return state

    if steps.get("submitted") and steps.get("clearinghouse_queued") and not steps.get("clearinghouse_accepted"):
        await log_and_emit("SUPERVISOR", "Waiting for clearinghouse review", state, status="WARNING")
        state["status"] = "PENDING_CLEARINGHOUSE"
        state["next"] = "finish"
        return state

    if steps.get("clearinghouse_accepted") and not steps.get("acknowledged"):

        steps["acknowledged"] = True
        state["pipeline"]["steps"] = steps

        state["status"] = "RUNNING"

        claim = (

            state.get("claim")
            or
            state.get("claim_data")
            or
            {}
        )

        claim["pipeline_status"] = "RUNNING"
        claim["pipeline_state"] = "RUNNING"
        claim["current_stage"] = "ACKNOWLEDGMENT"
        claim["current_agent"] = "ACKNOWLEDGMENT"
        claim["active_step"] = "acknowledgment"
        claim["progress"] = 85
        state["claim"] = claim

        await log_and_emit(
            "SUPERVISOR",
            "Clearinghouse accepted claim → resuming pipeline",
            state,
            status="SUCCESS"
        )

        await manager.broadcast({

            "type":"pipeline_resumed",
            "event":"pipeline_resumed",
            "claim_id":claim.get("claim_id"),
            "status":"RUNNING",
            "stage":"acknowledgment",
            "progress":85,
            "message":"Clearinghouse accepted claim. Resuming pipeline.",
            "timestamp":datetime.utcnow().isoformat()

        })

    if steps.get("submitted") and not steps.get("acknowledged") and not steps.get("clearinghouse_accepted"):
        await log_and_emit("SUPERVISOR", "Waiting for acknowledgment", state, status="WARNING")
        state["status"] = "PENDING_CLEARINGHOUSE"
        state["next"] = "finish"
        return state

    if steps.get("payment_processed") and steps.get("feedback_captured") and steps.get("learning_updated") and steps.get("analytics_done"):
        await log_and_emit("SUPERVISOR", "Pipeline completed", state, status="SUCCESS")
        pipeline_banner("PIPELINE COMPLETED SUCCESSFULLY", "🏁")
        claim = (

            state.get(
                "claim"
            )

            or

            state.get(
                "claim_data"
            )

            or

            {}
        )
        claim["pipeline_state"] = "COMPLETED"
        claim["pipeline_status"] = "COMPLETED"
        claim["current_stage"] = "COMPLETED"
        claim["current_agent"] = "NONE"
        claim["active_step"] = "completed"
        claim["progress"] = 100
        state["status"] = "COMPLETED"
        await manager.broadcast({
            "type": "pipeline_completed",
            "event": "pipeline_completed",
            "claim_id": claim.get("claim_id"),
            "status": "COMPLETED",
            "progress": 100,
            "current_stage": "COMPLETED",
            "current_agent": "NONE",
            "active_step": "completed",
            "claim": claim,
            "pipeline": state.get("pipeline", {}),
            "timestamp": datetime.utcnow().isoformat(),
        })
        # await asyncio.sleep(5)
        claim["workspace"] = "COMMAND_CENTER"
        state["claim"] = claim
        state["next"] = "finish"
        return state

    if not steps.get("eligibility_checked"):
        state["next"] = "eligibility"
        await log_and_emit("SUPERVISOR", "Routing → Eligibility Agent", state, status="ROUTE")
        return state

    if not steps.get("rules_validated"):
        state["next"] = "validation"
        await log_and_emit("SUPERVISOR", "Routing → Validation Agent", state, status="ROUTE")
        return state

    if not steps.get("compliance_checked"):
        state["next"] = "compliance"
        await log_and_emit("SUPERVISOR", "Routing → Compliance Agent", state, status="ROUTE")
        return state

    if not steps.get("case_orchestrated"):
        state["next"] = "case_orchestrator"
        await log_and_emit("SUPERVISOR", "Routing → Case Orchestrator", state, status="ROUTE")
        return state

    if not steps.get("submitted"):
        state["next"] = "submission"
        await log_and_emit("SUPERVISOR", "Routing → Submission Agent", state, status="ROUTE")
        return state

    if not steps.get("acknowledged"):
        state["next"] = "acknowledgment"
        await log_and_emit("SUPERVISOR", "Routing → Acknowledgment Agent", state, status="ROUTE")
        return state

    if not steps.get("denial_checked"):
        state["next"] = "denial"
        await log_and_emit("SUPERVISOR", "Routing → Denial Agent", state, status="ROUTE")
        return state

    if not steps.get("payment_processed"):
        state["next"] = "payment"
        await log_and_emit("SUPERVISOR", "Routing → Payment Agent", state, status="ROUTE")
        return state

    if not steps.get("feedback_captured"):
        state["next"] = "feedback_loop"
        await log_and_emit("SUPERVISOR", "Routing → Feedback Loop Agent", state, status="ROUTE")
        return state

    if not steps.get("learning_updated"):
        state["next"] = "learning"
        await log_and_emit("SUPERVISOR", "Routing → Learning Agent", state, status="ROUTE")
        return state

    if not steps.get("analytics_done"):
        state["next"] = "analytics"
        await log_and_emit("SUPERVISOR", "Routing → Analytics Agent", state, status="ROUTE")
        return state

    state["next"] = "finish"
    # await log_and_emit("SUPERVISOR", "Pipeline completed", state, status="SUCCESS")
    # pipeline_banner("PIPELINE COMPLETED SUCCESSFULLY", "🏁")
    return state


async def case_orchestrator(state):
    validation = state.get("validation", {})
    claim = state.get("claim", {})
    steps = state.get("pipeline", {}).get("steps", {})

    if validation.get("valid") is True:
        steps["case_orchestrated"] = True
        state["pipeline"]["steps"] = steps
        await log_and_emit("CASE_ORCHESTRATOR", "Validation passed; case creation skipped", state, status="INFO")
        return state

    if steps.get("case_orchestrated"):
        await log_and_emit("CASE_ORCHESTRATOR", "Case already orchestrated; skipping duplicate", state, status="INFO")
        return state

    case_id = f"CASE-{claim.get('claim_id')}"

    state["case"] = {
        "case_id": case_id,
        "status": "OPEN",
        "assigned_to": "QA_TEAM",
    }

    steps["case_orchestrated"] = True
    state["pipeline"]["steps"] = steps

    await log_and_emit("CASE_ORCHESTRATOR", "HITL REQUIRED", state, status="WARNING")
    await log_and_emit("CASE_ORCHESTRATOR", "Case created", state, status="INFO")
    await log_and_emit("CASE_ORCHESTRATOR", "Assigned to QA_TEAM", state, status="INFO")
    return state


async def claim_repair_node(state):
    repaired = await repair_engine.repair_and_retry(state, max_retries=1)
    steps = repaired.setdefault("pipeline", {}).setdefault("steps", {})
    steps["ai_suggestions"] = True
    steps["auto_corrected"] = bool(repaired.get("correction_history"))
    steps["validation_retry"] = True
    if repaired.get("validation", {}).get("valid") is True:
        steps["rules_validated"] = True
    return repaired


builder.add_node("supervisor", supervisor_node)
builder.add_node("case_orchestrator", create_logged_node("case_orchestrator", case_orchestrator))
builder.add_node("claim_repair", create_logged_node("claim_repair", claim_repair_node))
builder.add_node("eligibility", create_logged_node("eligibility", eligibility))
builder.add_node("validation", create_logged_node("validation", validation_agent))
builder.add_node("compliance", create_logged_node("compliance", compliance_agent))
builder.add_node("submission", create_logged_node("submission", submission))
builder.add_node("acknowledgment", create_logged_node("acknowledgment", acknowledgment))
builder.add_node("denial", create_logged_node("denial", denial))
builder.add_node("payment", create_logged_node("payment", payment))
builder.add_node("feedback_loop", create_logged_node("feedback_loop", feedback_agent))
builder.add_node("learning", create_logged_node("learning", learning_agent))
builder.add_node("analytics", create_logged_node("analytics", analytics))


def router(state):
    if not isinstance(state, dict):
        logger.error(
            "Invalid state",
            extra={
                "state_type": type(state).__name__
            }
            )
        return "finish"

    next_node = state.get("next")

    if not next_node:
        logger.error(
            "Missing 'next' in state",
            extra={
                "claim_id":( 
                    state.get("claim", {})
                           
                    if isinstance(state, dict)
                    else {}
                ).get("claim_id")
            }
        )
        return "finish"

    return next_node


builder.add_conditional_edges(
    "supervisor",
    router,
    {
        "case_orchestrator": "case_orchestrator",
        "claim_repair": "claim_repair",
        "eligibility": "eligibility",
        "validation": "validation",
        "compliance": "compliance",
        "submission": "submission",
        "acknowledgment": "acknowledgment",
        "denial": "denial",
        "payment": "payment",
        "feedback_loop": "feedback_loop",
        "learning": "learning",
        "analytics": "analytics",
        "finish": END,
    },
)

for node in [
    "case_orchestrator",
    "claim_repair",
    "eligibility",
    "validation",
    "compliance",
    "submission",
    "acknowledgment",
    "denial",
    "payment",
    "feedback_loop",
    "learning",
    "analytics",
]:
    builder.add_edge(node, "supervisor")

builder.set_entry_point("supervisor")
rcm_graph = builder.compile()

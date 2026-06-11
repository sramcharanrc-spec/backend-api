from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from app.intake.db_service import save_record
from pydantic import BaseModel
from typing import List
import json
from app.websocket.manager import manager
from app.utils.response_builder import build_clean_response
from app.intake.processor import process_document

from app.intake.db_service import get_record_by_id, save_record

from app.agents.denial.denial_agent import DenialAgent
from app.agents.acknowledgment.acknowledgment_agent import AcknowledgmentAgent
from app.agents.analytics.analytics_agent import AnalyticsAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.agents.feedback.feedback_agent import FeedbackLoopAgent
from app.agents.learning.learning_agent import LearningAgent
from app.agents.validation.validation_agent import ValidationAgent
from app.agents.submission.submission_agent import SubmissionAgent
# (add analytics later if needed)

from app.models.enums import ClaimStatusEnum






# -------------------------
# RCM Core
# -------------------------
from app.rcm.submit import submit_claim
from app.rcm.submission import (
    fetch_status,
    record_ack,
    record_denial,
)
from app.rcm.agentic_ai import predict_denial
from app.rcm.rcm_graph import rcm_graph
from fastapi import UploadFile, File
import asyncio
# -------------------------
# Utilities
# -------------------------
from app.utils.s3_reader import load_latest_claim_from_s3
from app.lambdas.claim_agent.claim_mapper import map_s3_json_to_claim
from app.lambdas.edi_agent.edi_835 import parse_edi_835
from app.lambdas.payment_agent.payment import post_payment
from app.lambdas.payment_agent.reconciliation import reconciliation_report
from app.lambdas.analytics_agent.analytics import get_kpis, analytics_dashboard
from app.services.analytics_service import get_metrics
from app.db.database import get_db
from sqlalchemy.orm import Session
from app.services.clearinghouse_orchestration_service import (
    ClearinghouseOrchestrationService,
    PENDING_CLEARINGHOUSE,
)
from app.rcm.ack_handler import parse_ack
from app.intake.db_service import update_record_status
from app.rcm.denial_835 import parse_835
from app.lambdas.Shared.store import (
    save_submission,
    get_all_submissions,
)

# -------------------------
# Helper
# -------------------------
def serialize(data):
    if isinstance(data, dict):
        return {k: serialize(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize(i) for i in data]
    elif hasattr(data, "value"):
        return data.value
    return data


# -------------------------
# Router
# -------------------------
router = APIRouter(tags=["RCM"])

BUCKET = "healthcare-edi-output"


# =========================
# Request Schemas
# =========================
class SubmitRequest(BaseModel):
    patient_id: str


class SubmitFromS3Request(BaseModel):
    patient_id: str


class BulkClaimAction(BaseModel):
    claim_ids: List[str]
    reviewer: str = "SYSTEM"


# =========================
# Health
# =========================
@router.get("/health")
def health():
    return {"status": "ok"}


# =========================
# Review (HITL)
# =========================
# Submit Claim (Manual)
# =========================


@router.post("/submit")
async def submit(file: UploadFile = File(...)):
    
    contents = await file.read()

    # 🔥 process file (PDF / JSON / etc)
    return {
        "message": "File received",
        "filename": file.filename
    }


# =========================
# Start Pipeline
# =========================


@router.post("/start-pipeline/{claim_id}")
async def start_pipeline(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    claim = record.get("claim", {})

    try:
        print("🚀 Running ValidationAgent...")
        validation_result = await ValidationAgent().run(claim)
        claim = validation_result["claim"]

        if not validation_result.get("valid", True):
            record["status"] = ClaimStatusEnum.VALIDATION_FAILED
            save_record(record)
            return {"message": "Validation failed"}

        print("🚀 Running SubmissionAgent...")
        submission_result = await SubmissionAgent().run(claim)
        claim = submission_result["claim"]

        # Pause in the clearinghouse review queue.
        record["pipeline"]["steps"]["rules_validated"] = True
        record["pipeline"]["steps"]["submitted"] = True
        record["pipeline"]["steps"]["clearinghouse_queued"] = True

        record["status"] = PENDING_CLEARINGHOUSE

        save_record(record)

        await manager.broadcast({
            "event": "clearinghouse_queued",
            "type": "clearinghouse_queued",
            "claim_id": claim_id,
            "status": PENDING_CLEARINGHOUSE,
        })

        return {
            "message": "Sent to clearinghouse review queue",
            "status": record["status"],
            "pipeline": record["pipeline"]
        }

    except Exception as e:
        print("❌ Pipeline error:", str(e))
        return {"error": str(e)}


# =========================
# 🚀 Submit From S3 + Pipeline
# =========================

@router.post("/submit-from-s3")
async def submit_from_s3(payload: SubmitFromS3Request):

    # -------------------------
    # 🔹 Step 1: Load S3 data
    # -------------------------
    try:
        raw_data = load_latest_claim_from_s3(
            bucket=BUCKET,
            patient_id=payload.patient_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"S3 error: {str(e)}"
        )

    if not raw_data:
        raise HTTPException(
            status_code=404,
            detail=f"No claim found in S3 for patient {payload.patient_id}"
        )

    # -------------------------
    # 🔹 Step 2: Map claim
    # -------------------------
    claim = map_s3_json_to_claim(raw_data)

    # -------------------------
    # 🔥 Step 3: VALIDATION
    # -------------------------
    print("🚀 Running ValidationAgent...")
    validation = await ValidationAgent().run(claim)

    claim = validation["claim"]

    if not validation.get("valid", True):
        return {
            "status": ClaimStatusEnum.VALIDATION_FAILED,
            "errors": validation.get("errors", [])
        }

    # -------------------------
    # 🔥 Step 4: SUBMISSION
    # -------------------------
    print("🚀 Running SubmissionAgent...")
    submission = await SubmissionAgent().run(claim)

    claim = submission["claim"]

    # -------------------------
    # 🔥 Step 5: STOP PIPELINE
    # -------------------------
    pipeline = {
        "steps": {
            "case_orchestrated": True,
            "eligibility_checked": True,
            "rules_validated": True,
            "submitted": True,
            "clearinghouse_queued": True,
            "acknowledged": False,
            "denial_checked": False,
            "paid": False,
            "analytics_done": False
        }
    }

    status = PENDING_CLEARINGHOUSE

    print(
       "🚀 Starting agent pipeline..."
    )

    pipeline["steps"].update({

        "clearinghouse_processing": True,
        "denial_ai_started": False,
        "payment_started": False,
        "learning_started": False,
        "analytics_started": False
    })

    await manager.broadcast({

        "type": "pipeline_update",

        "event": "pipeline_started",

        "claim_id":
            claim.get(
                "claim_id"
            ),

        "step":
            "clearinghouse",

        "status":
            "processing",

        "data": {

            "current_agent":
                "CLEARINGHOUSE",

            "current_stage":
                "CLEARINGHOUSE",

            "progress": 60
        }
    })

    # -------------------------
    # 🔹 Step 6: SAVE RECORD
    # -------------------------
    record = {
        "claim_id": claim.get("claim_id"),
        "file": None,
        "status": status,
        "claim": claim,
        "pipeline": pipeline,
        "case": {},
        "denial": None,
        "payment": None
    }

    save_record(record)

    # -------------------------
    # 🔹 Step 7: WS EVENT
    # -------------------------
    await manager.broadcast({
        "type": "clearinghouse_queued",
        "event": "clearinghouse_queued",
        "claim_id": claim.get("claim_id"),
        "step": "submission",
        "status": "completed",
        "data": {
            "status": status,
            "submission_id": claim.get("submission_id")
        }
    })

    print("⏸ Waiting for clearinghouse approval...")

    async def continue_pipeline(
        claim,
        record
    ):

        claim_id = claim.get(
            "claim_id"
        )

        try:

            # CLEARINGHOUSE

            await asyncio.sleep(3)

            record[
              "pipeline"
            ][
              "steps"
            ][
              "acknowledged"
            ] = True

            await manager.broadcast({

                "type": "pipeline_update",

                "claim_id":
                    claim_id,

                "step":
                    "clearinghouse",

                "status":
                    "completed",

                "data": {

                    "current_agent":
                        "CLEARINGHOUSE",

                    "current_stage":
                        "CLEARINGHOUSE_APPROVED",

                    "progress": 70
                }
            })

            # DENIAL AI

            await asyncio.sleep(2)

            record[
             "pipeline"
            ][
             "steps"
            ][
             "denial_checked"
            ] = True

            await manager.broadcast({

                "type": "pipeline_update",

                "claim_id":
                    claim_id,

                "step":
                    "denial_ai",

                "status":
                    "processing",

                "data": {

                    "current_agent":
                        "DENIAL_AI",

                    "current_stage":
                        "DENIAL_AI",

                    "progress": 80
                }
            })

            # PAYMENT

            await asyncio.sleep(2)

            record[
             "pipeline"
            ][
             "steps"
            ][
             "paid"
            ] = True

            record[
                "payment"
            ] = {

                "status":
                    "PAID",

                "amount":
                    claim.get(
                        "total_charge",
                        0
                    )
            }

            await manager.broadcast({

                "type": "pipeline_update",

                "claim_id":
                    claim_id,

                "step":
                    "payment",

                "status":
                    "completed",

                "data": {

                    "current_agent":
                        "PAYMENT",

                    "current_stage":
                        "PAYMENT",

                    "progress": 90
                }
            })

            # LEARNING + ANALYTICS

            await asyncio.sleep(2)

            record[
             "pipeline"
            ][
             "steps"
            ][
             "analytics_done"
            ] = True

            record[
                "status"
            ] = "COMPLETED"

            await manager.broadcast({

                "type": "claim_completed",

                "claim_id":
                    claim_id,

                "step":
                    "analytics",

                "status":
                    "completed",

                "data": {

                    "current_agent":
                        "ANALYTICS",

                    "current_stage":
                        "COMPLETED",

                    "progress": 100
                }
            })

            save_record(
                record
            )

        except Exception as e:

            print(
               f"Pipeline error:{e}"
            )

    # -------------------------
    # 🔹 Step 8: RESPONSE
    # -------------------------
    asyncio.create_task(

        continue_pipeline(
            claim,
            record
        )
    )

    return build_clean_response(record)

# =========================
# Submission Status
# =========================
@router.get("/status/{submission_id}")
def status(submission_id: str):
    return fetch_status(submission_id)


# =========================
# List Submissions
# =========================
@router.get("/list")
def list_submissions():
    return {"submissions": get_all_submissions()}


@router.get("/submissions")
def submissions():
    return {"submissions": get_all_submissions()}


# =========================
# ACK (277 / 999)
# =========================
@router.post("/ack")
async def receive_ack(payload: dict, db: Session = Depends(get_db)):
    claim_id = payload.get("claim_id")
    if claim_id and str(payload.get("status", "")).upper() in {"ACCEPTED", "ACCEPT", "APPROVED"}:
        try:
            return await ClearinghouseOrchestrationService(db).accept(
                claim_id,
                reviewer=payload.get("reviewer", "ACK"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    ack = parse_ack(payload)

    result = record_ack(
        submission_id=ack["submission_id"],
        status=ack["status"],
        reason=ack.get("reason"),
    )

    await manager.broadcast({
        "event": "ack_received",
        "data": result
    })

    return result


# =========================
# Denial (835)
# =========================
@router.post("/denial")
async def receive_denial(payload: dict, db: Session = Depends(get_db)):
    claim_id = payload.get("claim_id")
    if claim_id:
        try:
            return await ClearinghouseOrchestrationService(db).reject(
                claim_id,
                reviewer=payload.get("reviewer", "DENIAL"),
                reason=payload.get("reason") or payload.get("message"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    denial = parse_835(payload)

    result = record_denial(
        submission_id=denial["submission_id"],
        denial_code=denial["denial_code"],
        message=denial["message"]
    )

    await manager.broadcast({
        "event": "denial_received",
        "data": result
    })

    return result


# =========================
# Payment Posting
# =========================
@router.post("/payment")
async def payment(payload: dict):

    result = post_payment(payload)

    save_submission(
        submission_id=result["submission_id"],
        claim_id=None,
        status=result["status"],
        transmission_id=None,
        raw_edi="",
    )

    await manager.broadcast({
        "event": "payment_posted",
        "submission_id": result["submission_id"],
        "amount": result.get("paid_amount", 0)
    })

    return result


# =========================
# Denial Prediction
# =========================
@router.post("/predict-denial")
def predict(payload: dict):
    return predict_denial(payload)


# =========================
# Analytics
# =========================
@router.get("/analytics")
def analytics():
    return get_kpis()


@router.get("/analytics/dashboard")
async def dashboard():

    data = analytics_dashboard()

    await manager.broadcast({
        "type": "analytics_update",
        "event": "analytics_updated",
        "data": data
    })

    return data


# =========================
# EDI 835
# =========================
@router.post("/edi/835")
async def ingest_835(payload: dict):

    if "edi_835" in payload:
        parsed = parse_edi_835(payload["edi_835"])
    else:
        parsed = payload

    result = post_payment(parsed)

    await manager.broadcast({
        "event": "era_received",
        "data": result
    })

    return {
        "status": "835_RECEIVED",
        "submission_id": parsed.get("submission_id")
    }


# =========================
# Reconciliation
# =========================
@router.get("/reconciliation")
def reconciliation():
    return reconciliation_report()


# =========================
# WebSocket
# =========================
# @router.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):

#     await manager.connect(websocket)

#     try:
#         while True:
#             await websocket.receive_text()

#     except WebSocketDisconnect:
#         manager.disconnect(websocket)
#         print("❌ Client disconnected")


# =========================
# Agents Pipeline
# =========================
@router.get("/agents/pipeline")
def get_pipeline():
    return {
        "pipeline": [
            "Supervisor",
            "Eligibility",
            "Rules",
            "Submission",
            "Denial",
            "Payment",
            "Analytics"
        ]
    }

@router.get("/pipeline/{claim_id}")
def get_pipeline(claim_id: str):
    record = get_record_by_id(claim_id) # or DB fetch

    if not record:
        return {"error": "Not found"}

    return {
        "claim_id": claim_id,
        "stage": record.get("stage"),
        "pipeline": record.get("pipeline", {}),
        "claim": record.get("claim", {}),
        "financials": record.get("financials", {}),
        "ai": record.get("ai", {})
    }

# =========================
# Agent Status
# =========================
@router.get("/agents/status/{claim_id}")
def agent_status(claim_id: str):

    from app.intake.db_service import get_record_by_id
    from app.agents.base.base_agent import AGENT_CONFIG, AGENT_ORDER

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    claim = record.get("claim") if isinstance(record.get("claim"), dict) else {}
    pipeline = (
        record.get("pipeline")
        if isinstance(record.get("pipeline"), dict)
        else claim.get("pipeline", {})
    )
    steps = pipeline.get("steps", {}) if isinstance(pipeline, dict) else {}

    record_agents = (
        record.get("agents")
        if isinstance(record.get("agents"), dict)
        else {}
    )
    claim_agents = (
        claim.get("agents")
        if isinstance(claim.get("agents"), dict)
        else {}
    )
    saved_agents = record_agents or claim_agents

    def fallback_done(agent_key, step_flag):
        if agent_key == "supervisor":
            return bool(steps) or bool(saved_agents)
        if agent_key == "extraction":
            return (
                bool(steps.get(step_flag))
                or bool(steps.get("ocr_completed"))
                or bool(claim.get("extraction"))
            )
        if agent_key == "learning":
            return bool(steps.get(step_flag) or steps.get("learning_updated"))
        return bool(steps.get(step_flag))

    agents = []
    completed_count = 0
    completed_statuses = {
        "COMPLETED",
        "WARNING",
        "COMPLETED_WITH_WARNINGS",
        "NO_DENIAL",
        "DENIED",
        "PAID",
        "UNDERPAID",
        "WAITING_FOR_APPROVAL",
    }

    for agent_key in AGENT_ORDER:
        config = AGENT_CONFIG[agent_key]
        step_flag = config["step_flag"]
        existing_detail = saved_agents.get(agent_key)
        step_done = fallback_done(agent_key, step_flag)

        if isinstance(existing_detail, dict):
            detail = {
                "key": agent_key,
                "agent": config["agent"],
                "stage": config["stage"],
                "status": "COMPLETED" if step_done else "PENDING",
                "active_step": agent_key,
                "message": "",
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "progress": config["progress"],
                "passed": bool(step_done),
                "score": None,
                "risk_score": None,
                "risk_score_percent": None,
                "errors": [],
                "warnings": [],
                "output": {},
                "next_agent": None,
                **existing_detail,
            }
        else:
            detail = {
                "key": agent_key,
                "agent": config["agent"],
                "stage": config["stage"],
                "status": "COMPLETED" if step_done else "PENDING",
                "active_step": agent_key,
                "message": (
                    f"{config['agent']} completed"
                    if step_done
                    else f"{config['agent']} pending"
                ),
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "progress": config["progress"] if step_done else None,
                "passed": bool(step_done),
                "score": None,
                "risk_score": None,
                "risk_score_percent": None,
                "errors": [],
                "warnings": [],
                "output": {},
                "next_agent": None,
            }

        status = str(detail.get("status") or "").upper()
        if step_done or status in completed_statuses:
            completed_count += 1

        agents.append(detail)

    legacy_statuses = {
        "Supervisor": "completed" if fallback_done("supervisor", "supervisor_completed") else "pending",
        "Eligibility": "completed" if fallback_done("eligibility", "eligibility_checked") else "pending",
        "Rules": "completed" if fallback_done("validation", "rules_validated") else "pending",
        "Submission": "completed" if fallback_done("submission", "submitted") else "pending",
        "Denial": "completed" if fallback_done("denial", "denial_checked") else "pending",
        "Payment": "completed" if fallback_done("payment", "paid") else "pending",
        "Analytics": "completed" if fallback_done("analytics", "analytics_done") else "pending",
    }

    response = {
        "claim_id": claim_id,
        "status": record.get("status"),
        "pipeline_state": record.get("pipeline_state") or claim.get("pipeline_state"),
        "pipeline_status": record.get("pipeline_status") or claim.get("pipeline_status"),
        "current_stage": record.get("current_stage") or claim.get("current_stage"),
        "current_agent": record.get("current_agent") or claim.get("current_agent"),
        "active_step": record.get("active_step") or claim.get("active_step"),
        "progress": record.get("progress") if record.get("progress") is not None else claim.get("progress"),
        "completed_agents": completed_count,
        "total_agents": len(AGENT_ORDER),
        "agents": agents,
        "legacy_statuses": legacy_statuses,
        "updated_at": record.get("updated_at"),
    }
    response.update(legacy_statuses)
    return response

@router.get("/ai-suggestions/{claim_id}")
def get_ai_suggestions(claim_id: str):

    from app.intake.db_service import get_record_by_id

    record = get_record_by_id(claim_id)

    if not record:
        return {"suggestions": []}

    claim = record.get("claim", {})

    suggestions = []

    # 🔥 1. Missing NPI
    if not claim.get("provider", {}).get("npi") or claim["provider"]["npi"] == "?":
        suggestions.append({
            "field": "provider.npi",
            "reason": "Missing or invalid NPI",
            "fix": "Enter valid 10-digit NPI",
            "value": None,
        })

    # 🔥 2. Missing DOB
    if not claim.get("patient", {}).get("dob") or claim["patient"]["dob"] == "Unknown":
        suggestions.append({
            "field": "patient.dob",
            "reason": "Missing DOB",
            "fix": "Provide valid DOB",
            "value": "1990-01-01"
        })

    # 🔥 3. Missing CPT / Procedure
    services = claim.get("services", [])
    if services:
        for i, s in enumerate(services):
            if not s.get("cpt"):
                suggestions.append({
                    "field": f"services[{i}].cpt",
                    "reason": "Missing CPT code",
                    "fix": "Use valid CPT",
                    "value": "99213"
                })

    # 🔥 4. High denial risk
    risk = claim.get("denial_risk", {}).get("risk_score", 0)
    if risk > 0.7:
        suggestions.append({
            "field": "claim",
            "reason": "High denial risk",
            "fix": "Add ICD codes for medical necessity",
            "value": "Add ICD-10 diagnosis"
        })

    return {
        "claim_id": claim_id,
        "suggestions": suggestions
    }



@router.post("/approve/{claim_id}")
async def approve_claim(
    claim_id: str,
    db: Session = Depends(get_db),
    reviewer: str = "SYSTEM",
):
    """
    Approve a claim from manual/HITL review and resume downstream processing.

    This endpoint should be used by the HITL Approve button.

    Expected frontend call:
    POST /api/rcm/approve/{claim_id}?reviewer=Claim%20Workspace
    """

    print(f"✅ APPROVE TRIGGERED: {claim_id} by {reviewer}", flush=True)

    try:
        result = await ClearinghouseOrchestrationService(db).accept(
            claim_id,
            reviewer=reviewer,
        )

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:
        print(f"❌ APPROVE FAILED for {claim_id}: {exc}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve claim {claim_id}: {str(exc)}",
        ) from exc

    status = result.get("status") or "PROCESSING"
    stage = result.get("stage") or "ORCHESTRATION"
    pipeline = result.get("pipeline") or {}
    claim = result.get("claim") or {}

    await manager.broadcast(
        {
            "event": "pipeline_resumed",
            "type": "pipeline_resumed",
            "claim_id": claim_id,
            "agent": stage,
            "stage": stage,
            "status": status,
            "pipeline_state": status,
            "pipeline_status": status,
            "review_required": False,
            "approval_required": False,
            "pipeline_paused": False,
            "waiting_for_human": False,
            "pipeline": pipeline,
            "claim": claim,
        }
    )

    return {
        "message": "Clearinghouse accepted. Downstream processing resumed.",
        "claim_id": claim_id,
        "status": status,
        "stage": stage,
        "pipeline_state": status,
        "pipeline_status": status,
        "review_required": False,
        "approval_required": False,
        "pipeline_paused": False,
        "waiting_for_human": False,
        "pipeline": pipeline,
        "claim": claim,
    }

@router.post("/claim/{claim_id}/complete")
async def complete_claim(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    claim = record["claim"]

    # -------------------------
    # 🔥 Mark as completed
    # -------------------------
    claim["payment_status"] = "settled"
    claim["status"] = ClaimStatusEnum.COMPLETED.value.lower()

    # update pipeline
    record["pipeline"]["steps"]["paid"] = True

    # update final status
    record["status"] = ClaimStatusEnum.COMPLETED

    # -------------------------
    # 🔥 close case if exists
    # -------------------------
    if record.get("case"):
        record["case"]["status"] = "CLOSED"

    # -------------------------
    # 🔥 audit log
    # -------------------------
    from app.services.audit_service import log_audit

    log_audit(
        claim_id,
        "manual_settlement",
        "completed",
        {"action": "Patient paid remaining amount"}
    )

    # -------------------------
    # 🔥 save
    # -------------------------
    save_record(record)

    return {
        "message": "Claim marked as completed",
        "status": "COMPLETED"
    }

@router.post("/claim/{claim_id}/patient-pay")
async def patient_pay(claim_id: str):

    record = get_record_by_id(claim_id)
    if not record:
        return {"error": "Claim not found"}

    claim = record["claim"]
    payment = record.get("payment", {})

    remaining = payment.get("adjustment", 0)

    # -------------------------
    # 🔥 Mark as patient paid
    # -------------------------
    claim["payment_status"] = "settled"
    claim["settlement_type"] = "patient_paid"
    claim["patient_paid_amount"] = remaining

    record["status"] = ClaimStatusEnum.COMPLETED

    # close case if exists
    if record.get("case"):
        record["case"]["status"] = "CLOSED"

    # audit
    from app.services.audit_service import log_audit
    log_audit(claim_id, "patient_payment", "completed", {
        "amount": remaining
    })

    save_record(record)

    return {
        "message": "Patient paid remaining amount",
        "status": "COMPLETED"
    }

@router.post("/claim/{claim_id}/writeoff")
async def writeoff(claim_id: str):

    record = get_record_by_id(claim_id)
    if not record:
        return {"error": "Claim not found"}

    claim = record["claim"]
    payment = record.get("payment", {})

    adjustment = payment.get("adjustment", 0)

    # -------------------------
    # 🔥 Write-off logic
    # -------------------------
    claim["payment_status"] = "written_off"
    claim["settlement_type"] = "writeoff"
    claim["writeoff_amount"] = adjustment

    record["status"] = ClaimStatusEnum.COMPLETED

    # close case
    if record.get("case"):
        record["case"]["status"] = "CLOSED"

    # audit
    from app.services.audit_service import log_audit
    log_audit(claim_id, "writeoff", "completed", {
        "amount": adjustment
    })

    save_record(record)

    return {
        "message": "Amount written off",
        "status": "COMPLETED"
    }


# =========================
# 🤖 AUTO CLEARINGHOUSE MODE
# =========================
@router.post("/claim/{claim_id}/auto-accept")
async def auto_accept_claim(claim_id: str, db: Session = Depends(get_db)):
    """
    🤖 AUTO CLEARINGHOUSE MODE - Automatically accept and continue pipeline if quality metrics are good
    
    Decision criteria:
    - Validation score >= 80%
    - OCR confidence >= 75%  
    - Denial risk <= 70%
    - No compliance issues
    
    If all criteria met: Accept → Denial → Payment → Learning → Analytics
    If any criteria failed: Require manual review
    """
    try:
        result = await ClearinghouseOrchestrationService(db).auto_accept_if_qualified(claim_id, reviewer="SYSTEM_AUTO")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bulk-accept")
async def bulk_accept(payload: BulkClaimAction, db: Session = Depends(get_db)):
    return await ClearinghouseOrchestrationService(db).bulk_accept(payload.claim_ids, reviewer=payload.reviewer)


@router.post("/bulk-reject")
async def bulk_reject(payload: BulkClaimAction, db: Session = Depends(get_db)):
    return await ClearinghouseOrchestrationService(db).bulk_reject(payload.claim_ids, reviewer=payload.reviewer)


@router.post("/bulk-resubmit")
async def bulk_resubmit(payload: BulkClaimAction, db: Session = Depends(get_db)):
    return await ClearinghouseOrchestrationService(db).bulk_resubmit(payload.claim_ids, reviewer=payload.reviewer)

@router.post("/reject/{claim_id}")
async def reject_claim(claim_id: str, db: Session = Depends(get_db), reviewer: str = "SYSTEM"):

    try:
        return await ClearinghouseOrchestrationService(db).reject(claim_id, reviewer=reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    # 🔥 NEW: STATE VALIDATION
    current_status = record.get("status")

    if current_status == ClaimStatusEnum.COMPLETED:
        return {"error": "Cannot reject a completed claim"}

    if current_status != ClaimStatusEnum.PENDING_APPROVAL:
        return {"error": f"Cannot reject claim in {current_status} state"}

    # 🔥 Mark rejected
    record["status"] = ClaimStatusEnum.REJECTED

    # 🔥 Reset pipeline AFTER submission (but keep submitted=True)
    steps = record.get("pipeline", {}).get("steps", {})

    steps["resubmission_required"] = True  # ✅ Better than resetting submitted
    steps["acknowledged"] = False
    steps["denial_checked"] = False
    steps["paid"] = False
    steps["analytics_done"] = False

    record["pipeline"]["steps"] = steps

    # Optional: store reason
    record["rejection_reason"] = "Rejected at clearinghouse"

    save_record(record)

    return {
        "message": "Claim rejected. Sent back to validation.",
        "status": record["status"]
    }

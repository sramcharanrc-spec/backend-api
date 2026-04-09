from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
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
from app.agents.validation.validation_agent import ValidationAgent
from app.agents.submission.submission_agent import SubmissionAgent
# (add analytics later if needed)






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


# =========================
# Health
# =========================
@router.get("/health")
def health():
    return {"status": "ok"}


# =========================
# Review (HITL)
# =========================
@router.post("/review/{claim_id}/approve")
def approve_claim(claim_id: str):
    update_record_status(claim_id, "approved")
    return {"message": "Approved"}


@router.post("/review/{claim_id}/reject")
def reject_claim(claim_id: str):
    update_record_status(claim_id, "rejected")
    return {"message": "Rejected"}


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
            record["status"] = "VALIDATION_FAILED"
            save_record(record)
            return {"message": "Validation failed"}

        print("🚀 Running SubmissionAgent...")
        submission_result = await SubmissionAgent().run(claim)
        claim = submission_result["claim"]

        # ✅ STOP HERE
        record["pipeline"]["steps"]["rules_validated"] = True
        record["pipeline"]["steps"]["submitted"] = True

        record["status"] = "PENDING_APPROVAL"

        save_record(record)

        return {
            "message": "Sent to clearinghouse",
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
            "status": "VALIDATION_FAILED",
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
            "acknowledged": False,
            "denial_checked": False,
            "paid": False,
            "analytics_done": False
        }
    }

    status = "PENDING_APPROVAL"

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
        "type": "agent_event",
        "step": "submission",
        "status": "completed",
        "data": {
            "status": status,
            "submission_id": claim.get("submission_id")
        }
    })

    print("⏸ Waiting for clearinghouse approval...")

    # -------------------------
    # 🔹 Step 8: RESPONSE
    # -------------------------
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


# =========================
# ACK (277 / 999)
# =========================
@router.post("/ack")
async def receive_ack(payload: dict):

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
async def receive_denial(payload: dict):

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

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    pipeline = record.get("pipeline", {})

    steps = pipeline.get("steps", {})

    return {
        "Supervisor": "completed",

        "Eligibility": "completed" if steps.get("eligibility_checked") else "pending",

        "Rules": "completed" if steps.get("rules_validated") else "pending",

        "Submission": "completed" if steps.get("submitted") else "pending",

        "Denial": "completed" if steps.get("denial_checked") else "pending",

        "Payment": "completed" if steps.get("paid") else "pending",

        "Analytics": "completed" if steps.get("analytics_done") else "pending",
    }

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
            "value": "1234567890"
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
async def approve_claim(claim_id: str):

    print("✅ APPROVE TRIGGERED:", claim_id)

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    # 🔥 NEW: STATE VALIDATION (CRITICAL)
    current_status = record.get("status")

    if current_status == "COMPLETED":
        return {"error": "Claim already completed"}

    if current_status != "PENDING_APPROVAL":
        return {"error": f"Cannot approve claim in {current_status} state"}

    claim = record.get("claim", {})
    steps = record.get("pipeline", {}).get("steps", {})

    # ✅ 1. ACKNOWLEDGMENT
    if not steps.get("acknowledged"):
        print("🚀 Running AcknowledgmentAgent...")
        ack_result = await AcknowledgmentAgent().run(claim)
        claim = ack_result["claim"]
        steps["acknowledged"] = True

    # ✅ 2. DENIAL
    if not steps.get("denial_checked"):
        print("🚀 Running DenialAgent...")
        denial_result = await DenialAgent().run(claim)
        claim = denial_result["claim"]
        steps["denial_checked"] = True

    # ✅ 3. PAYMENT
    if not steps.get("paid"):
        print("🚀 Running PaymentAgent...")
        payment_result = await PaymentAgent().run(claim)
        claim = payment_result["claim"]
        steps["paid"] = True

    # ✅ 4. ANALYTICS
    if not steps.get("analytics_done"):
        print("🚀 Running AnalyticsAgent...")
        analytics_result = await AnalyticsAgent().run(claim)
        claim = analytics_result["claim"]
        steps["analytics_done"] = True

    # 🔥 UPDATE RECORD
    record["claim"] = claim
    record["pipeline"]["steps"] = steps

    # ✅ FINAL STATUS
    record["status"] = "COMPLETED"

    save_record(record)

    return {
        "message": "Pipeline resumed successfully",
        "status": record["status"],
        "pipeline": record["pipeline"]
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
    claim["status"] = "completed"

    # update pipeline
    record["pipeline"]["steps"]["paid"] = True

    # update final status
    record["status"] = "COMPLETED"

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

    record["status"] = "COMPLETED"

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

    record["status"] = "COMPLETED"

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

    record["status"] = "COMPLETED"

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

@router.post("/reject/{claim_id}")
async def reject_claim(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        return {"error": "Claim not found"}

    # 🔥 NEW: STATE VALIDATION
    current_status = record.get("status")

    if current_status == "COMPLETED":
        return {"error": "Cannot reject a completed claim"}

    if current_status != "PENDING_APPROVAL":
        return {"error": f"Cannot reject claim in {current_status} state"}

    # 🔥 Mark rejected
    record["status"] = "REJECTED"

    # 🔥 Reset pipeline AFTER submission
    steps = record.get("pipeline", {}).get("steps", {})

    steps["submitted"] = False
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
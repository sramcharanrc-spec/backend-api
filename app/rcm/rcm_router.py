from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.intake.db_service import save_record
from pydantic import BaseModel
from typing import List
import json
from app.websocket.manager import manager
from app.utils.response_builder import build_clean_response
from app.intake.processor import process_document
from app.intake.db_service import get_record_by_id
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

    print(f"🚀 Starting pipeline for {claim_id}")

    # 🔥 RUN IN BACKGROUND (NON-BLOCKING)
    asyncio.create_task(
        process_document("ehr-claims-bucket-agenticai", claim_id)
    )

    return {
        "status": "started",
        "claim_id": claim_id
    }



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
    mapped_claim = map_s3_json_to_claim(raw_data)

    # -------------------------
    # 🔥 Step 3: INITIAL STATE
    # -------------------------
    state = {
        "claim": mapped_claim,
        "stage": "start",
        "pipeline": {
            "steps": {
                "case_orchestrated": False,
                "eligibility_checked": False,
                "rules_validated": False,
                "submitted": False,
                "denial_checked": False,
                "paid": False,
                "analytics_done": False
            }
        }
    }

    # -------------------------
    # 🔹 Step 4: Run pipeline
    # -------------------------
    # -------------------------
# 🔹 Step 4: Run pipeline
# -------------------------
    try:
        await rcm_graph.ainvoke(
        state,
        {"recursion_limit": 50}
    )
    except Exception as e:
        print("❌ Pipeline execution error:", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {str(e)}"
        )

    # -------------------------
    # 🔥 Step 5: FINAL SAFE MERGE (CRITICAL FIX)
    # -------------------------


# LangGraph already mutates state → use it directly
    final_state = state

    print("🚀 FINAL PIPELINE STATE:", final_state.get("pipeline"))

    # -------------------------
    # 🔹 Step 6: WebSocket update
    # -------------------------
    await manager.broadcast({
        "type": "agent_event",
        "step": final_state.get("stage", "unknown"),
        "status": "completed",
        "data": final_state.get("pipeline", {})
    })

    # -------------------------
    # 🔹 Step 7: Save record
    # -------------------------
    save_record({
        "claim_id": final_state.get("claim", {}).get("claim_id"),
        "file": None,
        "status": final_state.get("claim", {}).get("status", "processed"),

        # core
        "claim": final_state.get("claim"),
        "pipeline": final_state.get("pipeline", {}),

        # orchestration
        "case": final_state.get("case", {}),

        # outputs
        "denial": final_state.get("claim", {}).get("denial_risk"),
        "payment": final_state.get("financials", {})
    })

    # -------------------------
    # 🔹 Step 8: Clean response
    # -------------------------
    clean_response = build_clean_response({
        "claim": final_state.get("claim"),
        "pipeline": final_state.get("pipeline"),
        "case": final_state.get("case", {}),
        "payment": final_state.get("financials", {})
    })

    return clean_response

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
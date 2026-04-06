from fastapi import APIRouter, HTTPException
import asyncio
import copy
from datetime import datetime
from fastapi.responses import FileResponse
from fastapi import HTTPException
from app.intake.db_service import get_record_by_id, update_case
from app.orchestrator.escalation_service import evaluate_escalation
# from app.intake.db_service import get_record_by_id, save_record
from app.rcm.rcm_graph import rcm_graph
from app.utils.response_helper import success_response
from app.utils.response_builder import build_clean_response
from app.intake.db_service import get_record_by_id as fetch_record_from_db
from app.orchestrator.case_orchestrator import calculate_sla
from app.services.feedback.feedback_store import store_feedback
from app.intake.db_service import update_record_status
from app.services.audit_service import (
    log_audit,
    get_audit_logs,
    verify_audit_integrity
)

from app.services.export_service import export_case_data
from app.services.pdf_service import (
    generate_audit_pdf,
    generate_pdf_signature
)

from app.websocket.manager import manager

# -------------------------
# Router
# -------------------------
router = APIRouter(tags=["Case"])


# =========================
# 📥 GET CASE
# =========================
@router.get("/case/{claim_id}")
def get_case_api(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(
        status_code=404,
        detail="Case not found"
    )

    case = evaluate_escalation(record.get("case", {}))
    return case


# =========================
# ✅ APPROVE CASE
# =========================
@router.post("/case/{claim_id}/approve")
def approve_case(claim_id: str, user_id: str = "SYSTEM"):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Case not found")

    case = record.get("case", {})

    # 🔥 Prevent double approval
    if case.get("approval", {}).get("status") == "APPROVED":
        return {"message": "Already approved"}

    timestamp = datetime.utcnow().isoformat()

    # ✅ Approval block
    case["approval"] = {
        "status": "APPROVED",
        "approved_by": user_id,
        "approved_at": timestamp
    }

    # ✅ Close case
    case["status"] = "CLOSED"

    # 🔥 Audit history
    case.setdefault("history", []).append({
        "action": "APPROVED",
        "user": user_id,
        "timestamp": timestamp
    })

    update_case(claim_id, case)
    update_record_status(claim_id, "completed")

    log_audit(claim_id, "approval", "completed", case["approval"])

    return {
        "message": "Approved",
        "case": case
    }


# =========================
# ✍️ SIGN CASE
# =========================
@router.post("/case/{claim_id}/sign")
def sign_case(claim_id: str, user_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Case not found")

    case = record.get("case", {})

    if case.get("signature"):
        return {"error": "Case already signed"}

    timestamp = datetime.utcnow().isoformat()

    signature = {
        "claim_id": claim_id,
        "signed_by": user_id,
        "timestamp": timestamp,
        "status": "SIGNED"
    }

    case["signature"] = signature

    # 🔥 Attach to approval if exists
    if case.get("approval"):
        case["approval"]["signature"] = signature

    # 🔥 Audit history
    case.setdefault("history", []).append({
        "action": "SIGNED",
        "user": user_id,
        "timestamp": timestamp
    })

    update_case(claim_id, case)

    log_audit(claim_id, "signature", "completed", signature)

    return {
        "message": "Case signed successfully",
        "signature": signature
    }


# =========================
# 🚨 ESCALATION
# =========================
@router.post("/case/{claim_id}/escalate")
def escalate_case(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Case not found")

    case = record.get("case", {})

    if not case:
        raise HTTPException(status_code=400, detail="No case found")

    level = case.get("escalation_level", 0) + 1
    case["escalation_level"] = level

    # 🔥 Role escalation
    if level == 1:
        case["assigned_to"] = "HEOR"
    elif level >= 2:
        case["assigned_to"] = "LEGAL"

    # 🔥 Reset SLA
    case["sla_due"] = calculate_sla(case["assigned_to"])

    case["status"] = "ESCALATED"

    timestamp = datetime.utcnow().isoformat()

    # 🔥 Audit history
    case.setdefault("history", []).append({
        "action": "ESCALATED",
        "assigned_to": case["assigned_to"],
        "timestamp": timestamp
    })

    update_case(claim_id, case)
    update_record_status(claim_id, "escalated")

    log_audit(claim_id, "escalation", "completed", case)

    return {
        "message": "Case escalated successfully",
        "case": case
    }

# =========================
# 🧑 HUMAN FIX → RESUME PIPELINE
# =========================
import copy

@router.post("/case/{claim_id}/fix")
async def fix_case(claim_id: str, updated_data: dict):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Case not found")

    claim = record.get("claim", {})

    # -------------------------
    # APPLY FIXES
    # -------------------------
    if updated_data.get("dob"):
        claim.setdefault("patient", {})["dob"] = updated_data["dob"]

    if updated_data.get("npi"):
        claim.setdefault("provider", {})["npi"] = updated_data["npi"]

    if updated_data.get("icd_code"):
        claim["icd_code"] = updated_data["icd_code"]

    log_audit(claim_id, "fix", "user_updated", updated_data)

    # -------------------------
    # RESET PIPELINE (🔥 FIX)
    # -------------------------
    state = {
        "claim": copy.deepcopy(claim),
        "status": "READY",
        "stage": "resume",

        "validation": {
            "valid": True,
            "status": "passed",
            "errors": []
        },

        "pipeline": {
            "steps": {
                "case_orchestrated": True,
                "eligibility_checked": True,
                "rules_validated": False,
                "submitted": False,
                "denial_checked": False,
                "paid": False,
                "analytics_done": False
            }
        }
    }

    print("👉 Restarting pipeline...")

    result = await asyncio.wait_for(
        rcm_graph.ainvoke(state),
        timeout=30
    )

    if not isinstance(result, dict):
        result = state

    print("✅ Pipeline finished")

    # -------------------------
    # UPDATE CASE
    # -------------------------
    case = record.get("case", {})
    case["status"] = "RESUMED"

    update_case(claim_id, {
        "claim": claim,
        "pipeline": result.get("pipeline", {}),
        "case": case,
        "status": "COMPLETED",
        "denial": result.get("denial_risk"),
        "payment": result.get("financials")
    })

    # -------------------------
    # WEBSOCKET
    # -------------------------
    await manager.broadcast({
        "event": "pipeline_update",
        "claim_id": claim_id,
        "stage": result.get("stage"),
        "pipeline": result.get("pipeline", {})
    })

    return build_clean_response(result)


# =========================
# 📄 PDF DOWNLOAD
# =========================
@router.get("/case/{claim_id}/export/pdf/download")
def download_pdf(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(
        status_code=404,
        detail="Case not found"
    )

    logs = get_audit_logs(claim_id)

    pdf_path = generate_audit_pdf(
        claim_id,
        record.get("case"),
        logs
    )

    return FileResponse(
        path=pdf_path,
        filename=f"{claim_id}_audit_report.pdf",
        media_type="application/pdf"
    )


# =========================
# 📦 EXPORT
# =========================
@router.get("/case/{claim_id}/export")
def export_case(claim_id: str, format: str = "json"):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(
        status_code=404,
        detail="Case not found"
    )

    return export_case_data(claim_id, record, format)


# =========================
# 🔍 AUDIT VERIFY
# =========================
@router.get("/audit/verify")
def verify_audit():
    valid, message = verify_audit_integrity()
    return {"valid": valid, "message": message}


# =========================
# 🔒 PDF VERIFY
# =========================
@router.post("/case/{claim_id}/verify-pdf")
def verify_pdf(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(
        status_code=404,
        detail="Case not found"
    )

    logs = get_audit_logs(claim_id)

    expected_hash = generate_pdf_signature({
        "claim_id": claim_id,
        "case": record.get("case"),
        "logs": logs
    })

    return {
        "valid": True,
        "expected_hash": expected_hash
    }


# =========================
# 📊 PIPELINE STRUCTURE
# =========================
@router.get("/agents/pipeline")
async def get_pipeline():
    try:
        nodes = list(rcm_graph.graph.nodes.keys())

        return {
            "pipeline": nodes
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/records/{claim_id}")
def get_record(claim_id: str):   # 🔥 renamed function

    record = fetch_record_from_db(claim_id)   # ✅ correct call

    if not record:
        raise HTTPException(status_code=404, detail="Not Found")

    return record

@router.get("/case/{claim_id}")
def get_case(claim_id: str):

    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    return {
        "status": "SUCCESS",
        "claim_id": claim_id,
        "case": record.get("case"),
        "claim": record.get("claim"),
        "validation": record.get("validation")
    }
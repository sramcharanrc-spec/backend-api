from fastapi import APIRouter, Depends, HTTPException
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
from app.intake.db_service import save_record
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
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.clearinghouse_orchestration_service import ClearinghouseOrchestrationService
from app.agents.submission.submission_agent import SubmissionAgent

# -------------------------
# Router
# -------------------------
router = APIRouter(tags=["Case"])

CLEARINGHOUSE_CASE_TYPES = {
    "CLEARINGHOUSE",
    "CLEARINGHOUSE_REVIEW",
    "PENDING_CLEARINGHOUSE",
    "WAITING_FOR_APPROVAL",
}

CLEARINGHOUSE_WAITING_STATUSES = {
    "WAITING_FOR_APPROVAL",
    "PENDING_CLEARINGHOUSE",
    "PENDING_APPROVAL",
}


def _approved_resume_state(record: dict, claim_id: str, user_id: str, timestamp: str) -> dict:
    claim = copy.deepcopy(record.get("claim", {}) or {})
    claim["claim_id"] = claim.get("claim_id") or claim_id
    claim["status"] = "APPROVED"
    claim["pipeline_stage"] = "submission_resume"
    claim["human_approved"] = True
    claim["human_approved_at"] = timestamp
    claim["human_approved_by"] = user_id

    pipeline = copy.deepcopy(record.get("pipeline") or {})
    steps = pipeline.setdefault("steps", {})
    steps.update({
        "eligibility_checked": True,
        "rules_validated": True,
        "compliance_checked": True,
        "case_orchestrated": True,
        "human_approved": True,
        "submitted": False,
        "clearinghouse_queued": False,
        "clearinghouse_accepted": False,
        "acknowledged": False,
        "denial_checked": False,
        "paid": False,
        "feedback_captured": False,
        "learning_updated": False,
        "analytics_done": False,
    })

    return {
        "claim_id": claim_id,
        "claim": claim,
        "pipeline": pipeline,
        "validation": {
            "valid": True,
            "errors": [],
            "human_approved": True,
            "human_approved_at": timestamp,
            "human_approved_by": user_id,
        },
        "status": "APPROVED",
        "stage": "SUBMISSION_RESUME",
        "resume_reason": "HITL_APPROVED",
    }


# =========================
# 📥 GET CASE
# =========================
def _is_clearinghouse_case(case: dict) -> bool:
    case_type = str(
        case.get("case_type")
        or case.get("stage")
        or case.get("type")
        or ""
    ).upper()
    return case_type in CLEARINGHOUSE_CASE_TYPES


def _is_waiting_for_clearinghouse(status: object) -> bool:
    return str(status or "").upper() in CLEARINGHOUSE_WAITING_STATUSES


def _resume_needs_clearinghouse_continuation(result: dict) -> bool:
    status = str(result.get("status") or result.get("claim", {}).get("status") or "").upper()
    stage = str(result.get("stage") or result.get("claim", {}).get("pipeline_stage") or "").upper()
    steps = (result.get("pipeline") or {}).get("steps") or {}
    return (
        status == "PENDING_CLEARINGHOUSE"
        or "CLEARINGHOUSE" in stage
        or (steps.get("submitted") and not steps.get("clearinghouse_accepted"))
    )


async def _continue_approved_resume(
    sql_service: ClearinghouseOrchestrationService,
    claim_id: str,
    resume_result: dict,
    reviewer: str,
) -> dict:
    claim = copy.deepcopy(resume_result.get("claim") or {})
    if not claim:
        return resume_result

    latest_sql_claim = sql_service.get_claim(claim_id)
    if not latest_sql_claim or (
        not _is_waiting_for_clearinghouse(latest_sql_claim.status)
        and _resume_needs_clearinghouse_continuation(resume_result)
    ):
        resume_result = sql_service.queue_after_submission(
            claim_id=claim_id,
            claim=claim,
            clearinghouse_response=claim.get("submission") or claim.get("clearinghouse"),
            artifacts=claim.get("generated_artifacts"),
            reviewer=reviewer,
        )

    latest_sql_claim = sql_service.get_claim(claim_id)
    if latest_sql_claim and _is_waiting_for_clearinghouse(latest_sql_claim.status):
        payload = latest_sql_claim.payload or {}
        sql_claim = payload.get("claim") or claim
        mode = str(
            sql_claim.get("clearinghouse_processing_mode")
            or sql_claim.get("processing_mode")
            or (payload.get("clearinghouse") or {}).get("processing_mode")
            or "MANUAL"
        ).upper()
        if mode == "AUTO":
            return await sql_service.auto_accept_if_qualified(claim_id, reviewer=reviewer)
        return sql_service.serialize(latest_sql_claim)

    return resume_result


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
async def approve_case(claim_id: str, user_id: str = "SYSTEM", db: Session = Depends(get_db)):
    """
    🔥 ENHANCED HITL APPROVAL - Resumes pipeline automatically after human approval
    
    Flow:
    1. Validate case exists (legacy or SQL)
    2. Prevent double approval
    3. Update claim record with APPROVED status
    4. Mark HITL as complete in pipeline
    5. Create/update SQL claim if needed
    6. Queue claim for pipeline resumption
    7. Broadcast websocket events for real-time UI updates
    """
    record = get_record_by_id(claim_id)
    sql_service = ClearinghouseOrchestrationService(db)
    sql_claim = sql_service.get_claim(claim_id)

    if not record and not sql_claim:
        raise HTTPException(status_code=404, detail="Case not found")

    case = record.get("case", {}) if record else {}
    is_clearinghouse_case = _is_clearinghouse_case(case)
    already_approved = case.get("approval", {}).get("status") == "APPROVED"

    timestamp = datetime.utcnow().isoformat()
    case["approval"] = {
        "status": "APPROVED",
        "approved_by": case.get("approval", {}).get("approved_by") or user_id,
        "approved_at": case.get("approval", {}).get("approved_at") or timestamp,
        "approval_enabled": False,
        "pipeline_resumed": True,
    }
    case["status"] = "APPROVED"
    if not already_approved:
        case.setdefault("history", []).append({"action": "APPROVED", "user": user_id, "timestamp": timestamp})

    if record:
        record["case"] = case
        record["status"] = "APPROVED"
        pipeline = record.setdefault("pipeline", {})
        steps = pipeline.setdefault("steps", {})
        steps["case_orchestrated"] = True
        steps["human_approved"] = True
        steps["validation_retry"] = False
        record["validation"] = {
            "valid": True,
            "errors": [],
            "human_approved": True,
            "human_approved_at": timestamp,
            "human_approved_by": user_id,
        }
        record.setdefault("claim", {})
        record["claim"]["status"] = "APPROVED"
        record["claim"]["pipeline_stage"] = "submission_resume"
        save_record(record)
        update_record_status(claim_id, "approved")
        log_audit(claim_id, "approval", "hitl_approved", case["approval"])

    if is_clearinghouse_case and sql_claim and _is_waiting_for_clearinghouse(sql_claim.status):
        resumed = await sql_service.accept(claim_id, reviewer=user_id)
        await manager.broadcast({
            "event": "pipeline_resumed",
            "type": "pipeline_resumed",
            "claim_id": claim_id,
            "stage": "CLEARINGHOUSE_ACCEPTED",
            "status": resumed.get("status", "PROCESSING"),
            "pipeline": resumed.get("pipeline", {}),
            "timestamp": timestamp,
        })
        await manager.send_pipeline_update(claim_id, "PIPELINE_RESUMED", resumed.get("pipeline", {}))
        return {
            "message": "Case approved and pipeline resumed from Clearinghouse",
            "case": case,
            "resumed": resumed,
            "approval_enabled": False,
        }

    claim = record.get("claim", {}) if record else {}
    resume_result = {}

    if claim:
        await manager.broadcast({
            "event": "hitl_approved",
            "type": "hitl_approved",
            "claim_id": claim_id,
            "stage": "SUBMISSION_RESUME",
            "step": "submission",
            "agent": "CASE_ORCHESTRATOR",
            "status": "PROCESSING",
            "message": "Approved Successfully. Pipeline Resumed.",
            "approval": case["approval"],
            "timestamp": timestamp,
        })

        resume_state = _approved_resume_state(record, claim_id, user_id, timestamp)
        try:
            resume_result = await rcm_graph.ainvoke(resume_state)
        except Exception as exc:
            resume_result = await SubmissionAgent().run(resume_state["claim"])
            log_audit(claim_id, "pipeline", "graph_resume_fallback", {"error": str(exc)})

        latest_sql_claim = sql_service.get_claim(claim_id)
        if is_clearinghouse_case and latest_sql_claim and _is_waiting_for_clearinghouse(latest_sql_claim.status):
            resume_result = await sql_service.accept(claim_id, reviewer=user_id)
        elif _resume_needs_clearinghouse_continuation(resume_result):
            resume_result = await _continue_approved_resume(sql_service, claim_id, resume_result, user_id)

        record["pipeline"] = resume_result.get("pipeline") or record.get("pipeline", {})
        record["status"] = resume_result.get("status") or "PROCESSING"
        record["claim"] = resume_result.get("claim") or record["claim"]
        record["claim"]["pipeline_stage"] = resume_result.get("stage") or "pipeline_resumed"
        save_record(record)
        update_record_status(claim_id, record["status"])
        log_audit(claim_id, "pipeline", "resumed_after_hitl_approval", {"status": resume_result.get("status")})

        await manager.broadcast({
            "event": "claim_status_updated",
            "type": "claim_status_updated",
            "claim_id": claim_id,
            "status": resume_result.get("status") or "PROCESSING",
            "stage": resume_result.get("stage") or "PIPELINE_RESUMED",
            "pipeline_stage": resume_result.get("stage") or "pipeline_resumed",
            "pipeline": resume_result.get("pipeline", {}),
            "claim": resume_result.get("claim", claim),
            "timestamp": timestamp,
        })
        await manager.broadcast({
            "event": "pipeline_resumed",
            "type": "pipeline_resumed",
            "claim_id": claim_id,
            "stage": resume_result.get("stage") or "PIPELINE_RESUMED",
            "status": resume_result.get("status") or "PROCESSING",
            "pipeline": resume_result.get("pipeline", {}),
            "claim": resume_result.get("claim", claim),
            "message": "Pipeline Resumed",
            "timestamp": timestamp,
        })
        await manager.send_pipeline_update(claim_id, resume_result.get("stage") or "PIPELINE_RESUMED", resume_result.get("pipeline", {}))

    resume_status = str(resume_result.get("status") or "APPROVED").upper()
    waiting_for_clearinghouse = resume_status in CLEARINGHOUSE_WAITING_STATUSES

    return {
        "message": (
            "HITL approved. Claim submitted and queued for clearinghouse review."
            if waiting_for_clearinghouse
            else "Case approved successfully and pipeline resumed"
        ),
        "case": case,
        "status": "WAITING_FOR_APPROVAL" if waiting_for_clearinghouse else resume_result.get("status") or "APPROVED",
        "pipeline_state": "WAITING_FOR_APPROVAL" if waiting_for_clearinghouse else resume_result.get("pipeline_state"),
        "current_stage": "CLEARINGHOUSE" if waiting_for_clearinghouse else resume_result.get("current_stage"),
        "review_required": True if waiting_for_clearinghouse else resume_result.get("review_required"),
        "pipeline_stage": resume_result.get("stage") or "pipeline_resumed",
        "resumed": resume_result,
        "approval_enabled": False,
        "timestamp": timestamp,
    }
    
    record = get_record_by_id(claim_id)
    sql_claim = ClearinghouseOrchestrationService(db).get_claim(claim_id)

    if not record and not sql_claim:
        raise HTTPException(status_code=404, detail="Case not found")

    # ❌ Prevent double approval
    case = record.get("case", {}) if record else {}
    if case.get("approval", {}).get("status") == "APPROVED":
        raise HTTPException(status_code=400, detail="Case already approved")

    timestamp = datetime.utcnow().isoformat()

    # ✅ Update case approval status
    case["approval"] = {
        "status": "APPROVED",
        "approved_by": user_id,
        "approved_at": timestamp,
        "approval_enabled": True,  # Flag to disable button on frontend
    }
    
    case["status"] = "APPROVED"  # NOT "CLOSED" - still in pipeline

    # 🔥 Audit history
    case.setdefault("history", []).append({
        "action": "APPROVED",
        "user": user_id,
        "timestamp": timestamp
    })

    # ========================
    # 🔄 UPDATE LEGACY RECORD
    # ========================
    if record:
        # Mark HITL review as complete
        record["case"] = case
        record["status"] = "APPROVED"
        
        # Update pipeline: mark HITL as done, prepare for validation retry
        pipeline = record.get("pipeline", {})
        steps = pipeline.get("steps", {})
        
        # ✅ Mark human review complete
        steps["case_orchestrated"] = True
        steps["human_approved"] = True
        steps["validation_retry"] = False  # Reset retry flag
        
        # Reset validation to retry with human-approved data
        record["validation"] = {
            "valid": True,  # Human approved, so mark as valid
            "errors": [],
            "human_approved": True,
            "human_approved_at": timestamp,
            "human_approved_by": user_id
        }
        
        pipeline["steps"] = steps
        record["pipeline"] = pipeline
        
        save_record(record)
        update_record_status(claim_id, "approved")
        log_audit(claim_id, "approval", "hitl_approved", case["approval"])
    
    # ========================
    # 🗄️ UPDATE SQL CLAIM
    # ========================
    sql_service = ClearinghouseOrchestrationService(db)
    
    if sql_claim:
        # Claim exists in SQL - check if it's in clearinghouse review
        if is_clearinghouse_case and _is_waiting_for_clearinghouse(sql_claim.status):
            # It's in clearinghouse - use accept flow
            resumed = await sql_service.accept(claim_id, reviewer=user_id)
            
            await manager.broadcast({
                "event": "pipeline_resumed",
                "type": "pipeline_resumed",
                "claim_id": claim_id,
                "stage": "CLEARINGHOUSE_ACCEPTED",
                "status": resumed.get("status", "PROCESSING"),
                "pipeline": resumed.get("pipeline", {}),
                "timestamp": timestamp,
            })
            
            return {
                "message": "✅ Case approved and pipeline resumed from Clearinghouse",
                "case": case,
                "resumed": resumed,
                "approval_enabled": False,  # Disable approve button
            }
    
    # ========================
    # 🎯 RESUME HITL PIPELINE
    # ========================
    # Queue claim for pipeline resumption with human approval
    claim = record.get("claim", {}) if record else {}
    
    if claim:
        from app.queue.queue_manager import claim_queue
        from app.queue.jobs import process_claim_job
        
        # Enqueue claim with skip_validation=True (human already approved)
        job = claim_queue.enqueue(
            process_claim_job,
            claim,
            skip_validation=True,  # Skip validation - human approved
            job_timeout='30m',
            job_id=f"resume-{claim_id}-{int(datetime.utcnow().timestamp())}"
        )
        
        log_audit(claim_id, "pipeline", "queued_for_resume", {"job_id": job.id})
        
        # 📢 Broadcast pipeline resumed
        await manager.broadcast({
            "event": "pipeline_resumed",
            "type": "pipeline_resumed",
            "claim_id": claim_id,
            "stage": "VALIDATION_RETRY",
            "status": "PROCESSING",
            "job_id": job.id,
            "message": f"🟢 Pipeline resumed after HITL approval",
            "timestamp": timestamp,
        })
        
        # 📢 Broadcast claim status
        await manager.broadcast({
            "event": "claim_status_updated",
            "type": "claim_status_updated",
            "claim_id": claim_id,
            "status": "APPROVED",
            "stage": "VALIDATION_RETRY",
            "pipeline_stage": "validation_retry",
            "timestamp": timestamp,
        })
    
    return {
        "message": "🟢 Case approved successfully and pipeline resumed",
        "case": case,
        "status": "APPROVED",
        "pipeline_stage": "validation_retry",
        "approval_enabled": False,  # Signal to frontend to disable button
        "timestamp": timestamp,
    }


# =========================
# ✍️ SIGN CASE
# =========================
@router.post("/case/{claim_id}/sign")
async def sign_case(claim_id: str, user_id: str):

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
    await manager.broadcast({
        "event": "case_signed",
        "type": "case_signed",
        "claim_id": claim_id,
        "status": "SIGNED",
        "signature": signature,
    })

    return {
        "message": "Case signed successfully",
        "signature": signature
    }


# =========================
# 🚨 ESCALATION
# =========================
@router.post("/case/{claim_id}/escalate")
async def escalate_case(claim_id: str):

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
    await manager.broadcast({
        "event": "case_escalated",
        "type": "case_escalated",
        "claim_id": claim_id,
        "status": "ESCALATED",
        "case": case,
    })

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
    # RESET PIPELINE (🔥 CORRECT)
    # -------------------------
    record["claim"] = claim

    record["pipeline"]["steps"] = {
        "case_orchestrated": True,
        "eligibility_checked": True,
        "rules_validated": False,
        "submitted": False,
        "acknowledged": False,
        "denial_checked": False,
        "paid": False,
        "analytics_done": False
    }

    record["status"] = "READY_FOR_APPROVAL"

    # -------------------------
    # UPDATE CASE STATUS
    # -------------------------
    case = record.get("case", {})
    case["status"] = "UPDATED"

    save_record(record)

    # -------------------------
    # WEBSOCKET (optional)
    # -------------------------
    await manager.broadcast({
        "event": "case_updated",
        "claim_id": claim_id
    })

    return {
        "message": "Case updated successfully. Ready for approval.",
        "status": record["status"]
    }


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

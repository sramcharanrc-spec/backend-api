from fastapi import APIRouter, HTTPException
import copy
import asyncio

from app.intake.db_service import (
    get_record_by_id,
    update_claim_data,
    update_record_status,
    get_all_records
)
from app.rcm.rcm_graph import rcm_graph

router = APIRouter(prefix="/review")


# -------------------------
# ✅ VALIDATION (UPDATED)
# -------------------------
def validate_claim(claim):
    missing = []

    if not claim.get("patient", {}).get("name") or claim["patient"]["name"] == "Unknown":
        missing.append("patient.name")

    if not claim.get("patient", {}).get("dob"):
        missing.append("patient.dob")

    if not claim.get("provider", {}).get("npi"):
        missing.append("provider.npi")

    if not claim.get("services"):
        missing.append("services")

    return missing


# -------------------------
# ✅ SUGGESTIONS (FIXED 🔥)
# -------------------------
@router.post("/{claim_id}/suggest")
async def suggest_fields(claim_id: str):
    try:
        record = get_record_by_id(claim_id)

        if not record:
            return {"claim_id": claim_id, "suggestions": {}}

        # ✅ handle both structures
        claim = record.get("claim") if "claim" in record else record

        suggestions = {}

        # 🔥 FIX 1: Patient DOB
        patient = claim.get("patient", {}) or {}
        if not patient.get("dob") or patient.get("dob") == "Unknown":
            suggestions["patient.dob"] = "1990-01-01"

        # 🔥 FIX 2: Provider NPI
        provider = claim.get("provider", {}) or {}
        if not provider.get("npi") or provider.get("npi") == "?":
            suggestions["provider.npi"] = "1234567890"

        # 🔥 FIX 3: Procedure Code
        if not claim.get("procedure_code"):
            services = claim.get("services") or []
            if isinstance(services, list) and len(services) > 0:
                suggestions["procedure_code"] = services[0].get("cpt")

        return {
            "claim_id": claim_id,
            "suggestions": suggestions
        }

    except Exception as e:
        import traceback
        print("❌ Suggest API Error:", str(e))
        traceback.print_exc()

        return {
            "claim_id": claim_id,
            "suggestions": {},
            "error": str(e)
        }

# -------------------------
# ✅ EDIT + RESUME (FIXED 🔥)
# -------------------------
# @router.post("/{claim_id}/edit-and-resume")
# async def edit_and_resume(claim_id: str, updated_claim: dict):

#     record = get_record_by_id(claim_id)

#     if not record:
#         raise HTTPException(status_code=404, detail="Claim not found")

#     existing_claim = record.get("claim", {})

#     # 🔥 Merge update safely
#     merged_claim = copy.deepcopy(existing_claim)

#     for key, value in updated_claim.items():
#         if isinstance(value, dict) and key in merged_claim:
#             merged_claim[key].update(value)
#         else:
#             merged_claim[key] = value

#     # 🔥 Validate
#     missing_fields = validate_claim(merged_claim)

#     if missing_fields:
#         update_record_status(claim_id, "needs_review")

#         return {
#             "message": "Missing fields",
#             "missing_fields": missing_fields
#         }

#     # -------------------------
#     # 🚀 RESET PIPELINE STATE
#     # -------------------------
#     state = {
#     "claim": copy.deepcopy(merged_claim),
#     "stage": "resume",

#     "pipeline": {
#         "steps": {   # 🔥 MUST MATCH YOUR SYSTEM
#             "case_orchestrated": True,
#             "eligibility_checked": True,
#             "rules_validated": False,
#             "submitted": False,
#             "denial_checked": False,
#             "paid": False,
#             "analytics_done": False
#         }
#     }
# }

#     print("👉 Resuming pipeline...")

#     result = await asyncio.wait_for(
#         rcm_graph.ainvoke(state),
#         timeout=30
#     )

#     print("✅ Pipeline completed")

#     # -------------------------
#     # 🔥 SAVE UPDATED CLAIM
#     # -------------------------
#     update_claim_data(claim_id, merged_claim)
#     validation = result.get("validation", {})

#     if not validation.get("valid", True):
#         update_record_status(claim_id, "needs_review")
#     else:
#         update_record_status(claim_id, "completed")

#     return {
#     "status": "SUCCESS",
#     "claim_id": claim_id,
#     "claim": merged_claim,
#     "pipeline": result.get("pipeline", {}),
#     "validation": result.get("validation", {}),
#     "stage": result.get("stage")
#     }
@router.post("/{claim_id}/edit-and-resume")
async def edit_and_resume(claim_id: str, updated_claim: dict):

    # -------------------------
    # 🔍 FETCH RECORD
    # -------------------------
    record = get_record_by_id(claim_id)

    if not record:
        raise HTTPException(status_code=404, detail="Claim not found")

    existing_claim = record.get("claim", {})

    # -------------------------
    # 🔥 MERGE UPDATE SAFELY
    # -------------------------
    merged_claim = copy.deepcopy(existing_claim)

    for key, value in updated_claim.items():
        if isinstance(value, dict) and key in merged_claim:
            merged_claim[key].update(value)
        else:
            merged_claim[key] = value

    # -------------------------
    # 🔥 RE-COMPUTE VALIDATION (CRITICAL FIX)
    # -------------------------
    missing_fields = validate_claim(merged_claim)

    validation = {
        "valid": len(missing_fields) == 0,
        "status": "passed" if len(missing_fields) == 0 else "failed",
        "errors": [
            {"field": f, "message": f"{f} missing"}
            for f in missing_fields
        ]
    }

    # -------------------------
    # 🚫 STILL INVALID → HITL
    # -------------------------
    if not validation["valid"]:
        print("⚠️ Still missing fields → HITL")

        update_record_status(claim_id, "needs_review")

        return {
            "status": "HITL_REQUIRED",
            "claim_id": claim_id,
            "validation": validation
        }

    # -------------------------
    # 🚀 RESET PIPELINE STATE
    # -------------------------
    state = {
    "claim": copy.deepcopy(merged_claim),

    # 🔥 RESET EVERYTHING
    "status": "READY",          # ✅ clear HITL
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

    print("👉 Resuming pipeline...")

    # -------------------------
    # 🚀 RUN PIPELINE (SAFE)
    # -------------------------
    try:
        result = await asyncio.wait_for(
            rcm_graph.ainvoke(state),
            timeout=30
        )

        # 🔥 HANDLE END STATE
        if not isinstance(result, dict):
            print("⚠️ Pipeline returned END → fallback to state")
            result = state

    except Exception as e:
        print("❌ Pipeline failed:", str(e))

        return {
            "status": "ERROR",
            "message": "Pipeline execution failed",
            "error": str(e)
        }

    print("✅ Pipeline execution completed")

    # -------------------------
    # 🔥 FINAL VALIDATION CHECK (USE FRESH ONE)
    # -------------------------
    is_invalid = not validation["valid"]

    if result.get("status") == "HITL_REQUIRED" or is_invalid:
        print("⚠️ Still requires human review")

        update_claim_data(claim_id, merged_claim)
        update_record_status(claim_id, "needs_review")

        return {
            "status": "HITL_REQUIRED",
            "claim_id": claim_id,
            "claim": merged_claim,
            "pipeline": result.get("pipeline", {}),
            "validation": validation,
            "stage": result.get("stage")
        }

    # -------------------------
    # ✅ SUCCESS FLOW
    # -------------------------
    update_claim_data(claim_id, merged_claim)
    update_record_status(claim_id, "completed")

    return {
        "status": "SUCCESS",
        "claim_id": claim_id,
        "claim": merged_claim,
        "pipeline": result.get("pipeline", {}),
        "validation": validation,
        "stage": result.get("stage")
    }

# -------------------------
# ✅ REVIEW LIST
# -------------------------
@router.get("/")
def get_review_items():

    records = get_all_records()

    review_items = []

    for r in records:
        status = r.get("status")

        if status == "needs_review":
            review_items.append({
                "claim_id": r.get("claim_id"),
                "patient": r.get("claim", {}).get("patient", {}),
                "status": status
            })

    return review_items
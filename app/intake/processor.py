import boto3
import uuid
import asyncio
from datetime import datetime
from datetime import datetime, timedelta




from app.intake.textract_service import analyze_document
from app.intake.db_service import save_record
from app.ai.claim_mapper_ai import map_claim_with_ai
from app.rcm.rcm_graph import rcm_graph
from app.ai.template_detection import detect_template_rule_based
from app.orchestrator.case_orchestrator import build_case_record
from app.websocket.manager import manager


# -------------------------
# 🔹 TEXTRACT PARSER
# -------------------------
def extract_key_values(textract_response):
    blocks = textract_response.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}

    kvs = {}

    for block in blocks:
        if block["BlockType"] == "KEY_VALUE_SET" and "KEY" in block.get("EntityTypes", []):

            key_text = ""
            value_text = ""

            # -------------------------
            # Extract KEY
            # -------------------------
            for rel in block.get("Relationships", []):
                if rel["Type"] == "CHILD":
                    for cid in rel["Ids"]:
                        word = block_map.get(cid)
                        if word and word["BlockType"] == "WORD":
                            key_text += word["Text"] + " "

            # -------------------------
            # Extract VALUE
            # -------------------------
            value_block = None
            for rel in block.get("Relationships", []):
                if rel["Type"] == "VALUE":
                    value_block = block_map.get(rel["Ids"][0])

            if value_block:
                for rel in value_block.get("Relationships", []):
                    if rel["Type"] == "CHILD":
                        for cid in rel["Ids"]:
                            word = block_map.get(cid)
                            if word and word["BlockType"] == "WORD":
                                value_text += word["Text"] + " "

            key = key_text.strip()
            value = value_text.strip()

            # 🔥 FIX: HANDLE DUPLICATE KEYS
            if key in kvs:
                if isinstance(kvs[key], list):
                    kvs[key].append(value)
                else:
                    kvs[key] = [kvs[key], value]
            else:
                kvs[key] = value

    # -------------------------
    # Tables
    # -------------------------
    tables = [b for b in blocks if b["BlockType"] == "TABLE"]
    kvs["tables_detected"] = len(tables)

    return kvs


# -------------------------
# 🧠 VALIDATION
# -------------------------
def should_go_to_human(claim, denial_risk):

    if not claim.get("patient", {}).get("dob") or claim["patient"]["dob"] == "Unknown":
        return True

    if claim.get("provider", {}).get("npi") in ["?", None]:
        return True

    if denial_risk and denial_risk.get("risk_score", 0) >= 0.5:
        return True

    return False


# -------------------------
# 🔥 MAIN FUNCTION
# -------------------------
# async def process_document(bucket, key):

#     print("📂 Bucket:", bucket)
#     print("📂 Key:", key)

#     s3 = boto3.client("s3")

#     # -------------------------
#     # ✅ Check file exists
#     # -------------------------
#     try:
#         s3.head_object(Bucket=bucket, Key=key)
#         print("✅ File exists in S3")
#     except Exception as e:
#         print("❌ File not found:", str(e))
#         raise

#     # -------------------------
#     # 📄 Textract
#     # -------------------------
#     textract_data = analyze_document(bucket, key)

#     # -------------------------
#     # 🧠 Extract
#     # -------------------------
#     extracted = extract_key_values(textract_data)
#     print("🧠 Extracted:", extracted)

#     # -------------------------
#     # 🧠 Template Detection
#     # -------------------------
#     template_result = detect_template_rule_based(extracted)

#     template = {
#         "template_name": template_result["template_name"],
#         "confidence": template_result["confidence"]
#     }

#     print("🧠 Template:", template)

#     # -------------------------
#     # 🤖 AI CLAIM
#     # -------------------------
#     try:
#         ai_claim = await map_claim_with_ai(extracted)

#         ai_claim["claim_id"] = f"CLM-{uuid.uuid4().hex[:10]}"
#         ai_claim["source"] = "AI_MAPPED"

#     except Exception as e:
#         print("❌ AI mapping failed:", str(e))

#         ai_claim = {
#             "claim_id": f"CLM-{uuid.uuid4().hex[:10]}",
#             "source": "FALLBACK",
#             "raw_extracted": extracted
#         }

#     # -------------------------
#     # 🚀 PIPELINE STATE (FIXED)
#     # -------------------------
#     state = {
#         "claim": ai_claim,
#         "stage": "start",
#         "pipeline": {
#             "eligibility_checked": False,
#             "rules_validated": False,
#             "submitted": False,
#             "denial_checked": False,
#             "paid": False,
#             "analytics_done": False
#         }
#     }

#     # -------------------------
#     # 🚀 RUN PIPELINE
#     # -------------------------
#     try:
#         pipeline_result = await rcm_graph.ainvoke(state)
#     except Exception as e:
#         print("❌ Pipeline failed:", str(e))
#         pipeline_result = None

#     # -------------------------
#     # 🔍 SAFE ACCESS
#     # -------------------------
#     denial_risk = pipeline_result.get("denial_risk") if pipeline_result else None

#     # -------------------------
#     # 🔥 HUMAN-IN-LOOP
#     # -------------------------
#     if should_go_to_human(ai_claim, denial_risk):

#         print("⚠️ HUMAN REVIEW REQUIRED")

#         status = "needs_review"
#         pipeline_result = None

#     else:
#         print("✅ Auto processed")
#         status = "SUCCESS"

#     # -------------------------
#     # 🧠 CASE RECORD
#     # -------------------------
#     case_data = build_case_record(ai_claim, denial_risk)

#     # -------------------------
#     # 📡 WEBSOCKET UPDATE (FIXED)
#     # -------------------------
#     await manager.broadcast({
#         "event": "pipeline_update",
#         "claim_id": ai_claim["claim_id"],
#         "status": status,
#         "pipeline": pipeline_result or {}
#     })

#     # -------------------------
#     # 📦 FINAL RESULT
#     # -------------------------
#     result = {
#         "claim_id": ai_claim["claim_id"],
#         "file": key,
#         "template": template,
#         "status": status,

#         "claim": ai_claim,
#         "pipeline": pipeline_result or {},

#         "denial": pipeline_result.get("denial") if pipeline_result else None,
#         "payment": pipeline_result.get("payment") if pipeline_result else None,

#         "case": case_data,
#         "created_at": datetime.utcnow().isoformat()
#     }

#     print("🧠 FINAL ITEM:", result)

#     # -------------------------
#     # 💾 SAVE
#     # -------------------------
#     save_record(result)

#     return result



async def process_document(bucket, key):

    print("📂 Bucket:", bucket)
    print("📂 Key:", key)

    s3 = boto3.client("s3")

    # -------------------------
    # ✅ Check file exists
    # -------------------------
    try:
        s3.head_object(Bucket=bucket, Key=key)
        print("✅ File exists in S3")
    except Exception as e:
        print("❌ File not found:", str(e))
        raise

    # -------------------------
    # 📄 Textract
    # -------------------------
    textract_data = analyze_document(bucket, key)

    # -------------------------
    # 🧠 Extract
    # -------------------------
    extracted = extract_key_values(textract_data)
    print("🧠 Extracted:", extracted)

    # -------------------------
    # 🧠 Template Detection
    # -------------------------
    template_result = detect_template_rule_based(extracted)

    template = {
        "template_name": template_result["template_name"],
        "confidence": template_result["confidence"]
    }

    print("🧠 Template:", template)

    # -------------------------
    # 🤖 AI CLAIM
    # -------------------------
    try:
        ai_claim = await map_claim_with_ai(extracted)

        ai_claim["claim_id"] = f"CLM-{uuid.uuid4().hex[:10]}"
        ai_claim["source"] = "AI_MAPPED"

    except Exception as e:
        print("❌ AI mapping failed:", str(e))

        ai_claim = {
            "claim_id": f"CLM-{uuid.uuid4().hex[:10]}",
            "source": "FALLBACK",
            "raw_extracted": extracted
        }

    # -------------------------
    # 🚀 INITIAL STATE
    # -------------------------
    state = {
        "claim": ai_claim,
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
    # 🚀 RUN PIPELINE
    # -------------------------
    try:
        pipeline_result = await asyncio.wait_for(
            rcm_graph.ainvoke(state),
            timeout=30
        )

        if not isinstance(pipeline_result, dict):
            print("⚠️ LangGraph returned END → fallback to state")
            pipeline_result = state

    except Exception as e:
        print("❌ Pipeline failed:", str(e))
        pipeline_result = state

    # -------------------------
    # 🔥 ENSURE STRUCTURE
    # -------------------------
    if "validation" not in pipeline_result:
        pipeline_result["validation"] = {
            "valid": False,
            "status": "failed",
            "errors": ["Validation missing"]
        }

    validation = pipeline_result.get("validation") or {}

    if "status" not in pipeline_result:
        pipeline_result["status"] = "HITL_REQUIRED"

    # -------------------------
    # 🔍 SAFE ACCESS
    # -------------------------
    claim_data = pipeline_result.get("claim", ai_claim)
    denial_risk = claim_data.get("denial_risk")

    # -------------------------
    # 🔥 HITL DECISION
    # -------------------------
    is_invalid = (
        not validation
        or validation.get("valid") is False
        or validation.get("status") == "failed"
        or bool(validation.get("errors"))
    )

    status = "SUCCESS"

    if pipeline_result.get("status") == "HITL_REQUIRED":
        print("⛔ HITL from pipeline")
        status = "HITL_REQUIRED"

    elif is_invalid:
        print("⛔ Validation failed")
        status = "HITL_REQUIRED"

    elif should_go_to_human(claim_data, denial_risk):
        print("⚠️ Business rule HITL")
        status = "HITL_REQUIRED"

    print("🔥 FINAL STATUS:", status)

    # -------------------------
    # 🔥 HITL REASON
    # -------------------------
    hitl_reason = validation.get("errors", [])

    # -------------------------
    # 📁 CASE CREATION (FIXED)
    # -------------------------
    case_data = pipeline_result.get("case")

    if status == "HITL_REQUIRED":
        print("📁 Creating / Updating HITL case")

        case_data = {
            "case_id": case_data.get("case_id") if case_data else f"CASE-{uuid.uuid4().hex[:6]}",
            "type": "HITL",
            "status": "OPEN",
            "assigned_to": "MA",
            "priority": "HIGH",

            # 🔥 CRITICAL
            "issues": hitl_reason,

            "created_at": datetime.utcnow().isoformat(),
            "sla_due": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
            "escalation_level": 0
        }

    # -------------------------
    # 📡 WEBSOCKET
    # -------------------------
    await manager.broadcast({
        "event": "pipeline_update",
        "claim_id": claim_data["claim_id"],
        "status": status,
        "pipeline": pipeline_result.get("pipeline", {})
    })

    # -------------------------
    # 📦 FINAL RESULT
    # -------------------------
    final_result = {
        "claim_id": claim_data["claim_id"],
        "file": key,
        "template": template,
        "status": status,

        "claim": claim_data,
        "pipeline": pipeline_result.get("pipeline", {}),

        # 🔥 FIXED
        "validation": validation,

        "hitl": {
            "required": status == "HITL_REQUIRED",
            "reason": hitl_reason,
            "assigned_to": case_data.get("assigned_to") if case_data else None
        },

        "denial": claim_data.get("denial_risk"),
        "payment": pipeline_result.get("financials"),

        "case": case_data,
        "created_at": datetime.utcnow().isoformat()
    }

    print("🧠 FINAL ITEM:", final_result)

    # -------------------------
    # 💾 SAVE
    # -------------------------
    save_record(final_result)

    return final_result
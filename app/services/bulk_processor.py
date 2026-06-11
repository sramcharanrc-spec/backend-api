import os
import uuid
import asyncio
import time
import logging
from datetime import datetime
from typing import List, Dict, Any

from app.rcm.rcm_graph import rcm_graph
from app.agents.validation.validation_agent import ValidationAgent
from app.websocket.manager import manager
from app.rcm.claim_store import bulk_insert_claims, create_case, save_claim

# -------------------------
# ⚙️ CONFIG
# -------------------------
CONCURRENT_LIMIT = min(50, (os.cpu_count() or 4) * 5)
CHUNK_SIZE = 500
BATCH_TIMEOUT = 120

logger = logging.getLogger("bulk_processor")
logger.setLevel(logging.INFO)


# -------------------------
# 🔁 RETRY WRAPPER
# -------------------------
async def retry_wrapper(func, retries=3, delay=1):
    for attempt in range(retries):
        try:
            return await func()
        except Exception as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay * (2 ** attempt))


# -------------------------
# 📬 DLQ (Dead Letter Queue)
# -------------------------
async def send_to_dlq(claim_id, error, payload):
    try:
        create_case(
            claim_id=claim_id,
            error=error,
            case_type="DLQ"
        )
        logger.error(f"📬 DLQ: {claim_id} → {error}")
    except Exception as e:
        logger.error(f"❌ DLQ FAILED: {str(e)}")


# -------------------------
# 🧠 CLAIM PIPELINE
# -------------------------
async def run_claim_pipeline(mapped_claim):

    claim_id = mapped_claim["claim_id"]

    save_claim(
        claim_id=claim_id,
        status="PROCESSING",
        stage="VALIDATION",
        payload=mapped_claim,
        total_charge=mapped_claim.get("total_charge", 0)
    )

    validation_agent = ValidationAgent()

    # -------------------------
    # VALIDATION
    # -------------------------
    validation = await retry_wrapper(
        lambda: validation_agent.run({"claim": mapped_claim})
    )

    if validation.get("validation", {}).get("valid") is False:

        create_case(
            claim_id=claim_id,
            error=validation.get("validation", {}).get("errors", [])
        )

        save_claim(
            claim_id=claim_id,
            status="HITL_REQUIRED",
            stage="VALIDATION",
            payload=mapped_claim,
            total_charge=mapped_claim.get("total_charge", 0)
        )

        return {
            "claim_id": claim_id,
            "status": "HITL_REQUIRED",
            "payload": mapped_claim,
            "validation": validation.get("validation", {})
        }

    # -------------------------
    # PIPELINE
    # -------------------------
    state = {
        "claim": validation.get("claim", mapped_claim),
        "pipeline": {"steps": {}}
    }

    pipeline_result = await retry_wrapper(
        lambda: rcm_graph.ainvoke(state)
    )

    if not isinstance(pipeline_result, dict):
        pipeline_result = state

    steps = pipeline_result.get("pipeline", {}).get("steps", {})

    if steps.get("submitted") and not steps.get("acknowledged"):
        status = "PENDING_APPROVAL"
    elif steps.get("paid") and steps.get("analytics_done"):
        status = "COMPLETED"
    else:
        status = "PROCESSING"

    final_claim = pipeline_result.get("claim", mapped_claim)

    save_claim(
        claim_id=claim_id,
        status=status,
        stage="PIPELINE",
        payload=final_claim,
        total_charge=final_claim.get("total_charge", 0)
    )

    return {
        "claim_id": claim_id,
        "status": status,
        "payload": final_claim,
        "pipeline": pipeline_result.get("pipeline", {}),
        "validation": validation.get("validation", {})
    }


# -------------------------
# 🚀 SINGLE CLAIM
# -------------------------
async def process_single_claim(row: Dict, idx: int):

    claim_id = f"CLM-{uuid.uuid4().hex[:10]}"

    # -------------------------
    # BUILD CLAIM
    # -------------------------
    mapped_claim = {
        "claim_id": claim_id,
        "patient": {
            "name": str(row.get("Patient", "Unknown")),
            "dob": str(row.get("DOB", "1990-01-01"))
        },
        "provider": {
            "npi": str(row.get("NPI", ""))
        },
        "payer": {
            "name": str(row.get("Payer", "UNKNOWN"))
        },
        "services": [{
            "cpt": str(row.get("CPT", "99214")),
            "charge": float(row.get("Charge", 100)),
            "units": int(row.get("Units", 1))
        }],
        "total_charge": float(row.get("Charge", 100))
    }

    try:
        result = await run_claim_pipeline(mapped_claim)

        # 🔥 Throttled WebSocket
        if idx % 10 == 0:
            await manager.send_event("progress", {
                "claim_id": claim_id,
                "status": result["status"]
            })

        return result

    except Exception as e:
        try:
            await send_to_dlq(claim_id, str(e), mapped_claim)
        except Exception:
            logger.exception("DLQ failed")

        return {
            "claim_id": claim_id,
            "status": "FAILED",
            "error": str(e),
            "payload": mapped_claim
        }


# -------------------------
# 🚀 BATCH PROCESSOR
# -------------------------
async def process_claims_batch(data: List[Dict]):

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

    async def worker(idx, row):
        async with semaphore:
            return await process_single_claim(row, idx)

    tasks = [worker(i, row) for i, row in enumerate(data)]

    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=BATCH_TIMEOUT
    )

    bulk_data = []
    success = 0
    failed = 0

    for res in results:

        if isinstance(res, Exception):
            failed += 1
            continue

        if res["status"] in ["COMPLETED", "PROCESSING", "PENDING_APPROVAL"]:
            success += 1
        else:
            failed += 1

        bulk_data.append({
            "claim_id": res["claim_id"],
            "status": res["status"],
            "payload": res.get("payload"),
            "pipeline": res.get("pipeline", {})
        })

    # -------------------------
    # 💾 DB INSERT
    # -------------------------
    bulk_insert_claims(bulk_data)

    return {
        "total": len(data),
        "success": success,
        "failed": failed
    }


# -------------------------
# 🚀 BULK ENTRY (1 LAKH READY)
# -------------------------
async def process_bulk_claims(all_data: List[Dict]):

    logger.info(f"🚀 TOTAL CLAIMS: {len(all_data)}")

    final_summary = {
        "total": len(all_data),
        "success": 0,
        "failed": 0
    }

    start = time.time()

    # -------------------------
    # 🔥 CHUNKING
    # -------------------------
    for i in range(0, len(all_data), CHUNK_SIZE):

        chunk = all_data[i:i + CHUNK_SIZE]

        logger.info(f"⚡ Processing chunk {i} → {i + len(chunk)}")

        result = await process_claims_batch(chunk)

        final_summary["success"] += result["success"]
        final_summary["failed"] += result["failed"]

    logger.info(f"⏱ TOTAL TIME: {round(time.time() - start, 2)} sec")

    return final_summary

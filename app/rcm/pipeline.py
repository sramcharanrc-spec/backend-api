import time
import asyncio
from app.rcm.websocket.manager import manager
from app.rcm.clearinghouse_client import send_to_clearinghouse
from app.rcm.submission import (
    record_ack,
    record_denial,
    record_success,
    save_submission,
    get_submission
)
from app.rcm.edi_responses import (
    generate_999_ack,
    generate_277ca,
    generate_era_835
)

def safe_broadcast(data):
    asyncio.create_task(manager.broadcast(data))


def execute_pipeline(payload: dict) -> dict:

    submission_id = payload.get("submission_id")

    # 🔥 1. VALIDATION
    safe_broadcast({"stage": "validation", "status": "running"})

    validation = validate_claim(payload)

    if not validation["valid"]:
        safe_broadcast({
            "stage": "validation",
            "status": "failed",
            "errors": validation["errors"]
        })
        return {
            "submission_id": submission_id,
            "status": "EDA_FAILED",
            "errors": validation["errors"]
        }

    safe_broadcast({"stage": "validation", "status": "completed"})
    time.sleep(0.5)

    # 🔥 2. EDI GENERATION
    safe_broadcast({"stage": "edi_generation", "status": "running"})

    edi_payload = f"EDI837::{submission_id}"

    safe_broadcast({
        "stage": "edi_generation",
        "status": "completed",
        "edi": edi_payload
    })

    print("✅ Sending EDI:", edi_payload)
    time.sleep(0.5)

    # 🔥 3. CLEARINGHOUSE
    safe_broadcast({"stage": "clearinghouse", "status": "running"})

    ch_response = send_to_clearinghouse(edi_payload)

# ✅ Save submission
    record_success(payload, {
        "transmission_id": ch_response.get("transmission_id"),
        "edi": edi_payload
    })

    safe_broadcast({
        "stage": "clearinghouse",
        "status": "completed",
        "response": ch_response
    })

    time.sleep(0.5)

    # 🔥 4. 999 ACK
    ack_999 = generate_999_ack()

    record_ack(
    submission_id=submission_id,
    status=ack_999["status"],
    reason=ack_999["message"],
    claim_id=payload.get("claim_id")
    )

    safe_broadcast({
        "stage": "ack_999",
        "status": ack_999["status"],
        "data": ack_999
    })

    time.sleep(0.5)

    # 🔥 5. 277CA
    ack_277 = generate_277ca(submission_id, True)

    record_ack(
    submission_id=submission_id,
    status=ack_277["status"],
    reason=ack_277.get("error"),
    claim_id=payload.get("claim_id")
    )

    safe_broadcast({
        "stage": "277ca",
        "status": ack_277["status"],
        "data": ack_277
    })

    time.sleep(0.5)

    # 🔥 6. DENIAL CHECK
    safe_broadcast({"stage": "denial_check", "status": "running"})

    ai = predict_denial(payload)

    if ai.get("denial_risk", 0) > 0.7:

        record_denial(
            submission_id=submission_id,
            denial_code="CO-50",
            message="AI predicted denial"
        )

        safe_broadcast({
            "stage": "denial",
            "status": "denied"
        })

        return {
            "submission_id": submission_id,
            "status": "DENIED"
        }

    safe_broadcast({"stage": "denial_check", "status": "cleared"})
    time.sleep(0.5)

    # 🔥 7. ERA 835
    era = generate_era_835(
        submission_id,
        float(payload.get("total_charge", 0))
    )

    record_success(payload, {
    "transmission_id": submission_id,
    "edi": str(era)
    })

    safe_broadcast({
        "stage": "era_835",
        "status": "PAID",
        "data": era
    })

    time.sleep(0.5)

    # 🔥 8. PAYMENT
    safe_broadcast({"stage": "payment", "status": "running"})

    total_charge = float(payload.get("total_charge", 0))

    post_payment({
        "submission_id": submission_id,
        "expected_amount": total_charge,
        "paid_amount": total_charge
    })

    safe_broadcast({"stage": "payment", "status": "completed"})

    return {
        "submission_id": submission_id,
        "status": "PAID"
    }
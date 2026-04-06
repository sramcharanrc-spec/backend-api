# app/rcm/ack_handler.py

def parse_ack(payload: dict) -> dict:
    raw_status = payload.get("status", "").upper()

    if raw_status == "ACCEPTED":
        internal_status = "ACK_RECEIVED"
    elif raw_status in ["REJECTED", "ERROR"]:
        internal_status = "ACK_REJECTED"
    else:
        internal_status = "UNKNOWN"

    return {
        "submission_id": payload["submission_id"],
        "status": internal_status,
        "reason": payload.get("reason")
    }

from app.lambdas.Shared.store import save_submission, get_submission


import uuid

# -------------------------
# EDA / validation failure
# -------------------------
def record_failure(payload, errors):
    save_submission(
        submission_id=payload["submission_id"],
        claim_id=payload["claim_id"],   # ✅ ensure claim_id is saved
        status="EDA_FAILED",
        transmission_id=None,
        raw_edi=""
    )

    return {
        "submission_id": payload["submission_id"],
        "status": "EDA_FAILED",
        "errors": errors
    }


# -------------------------
# Successful submission
# -------------------------
def record_success(payload, transmission):
    save_submission(
        submission_id=payload["submission_id"],
        claim_id=payload["claim_id"],   # ✅ ensure claim_id is saved
        status="SUBMITTED",
        transmission_id=transmission.get("transmission_id"),
        raw_edi=transmission.get("edi", "")
    )

    return {
        "submission_id": payload["submission_id"],
        "status": "SUBMITTED",
        "transmission_id": transmission.get("transmission_id")
    }


# -------------------------
# 277CA / 999 acknowledgment
# -------------------------
def record_ack(
    submission_id: str,
    status: str,
    reason: str | None,
    claim_id: str | None = None
):


    print("ACK updating submission:", submission_id)

    save_submission(
        submission_id=submission_id,
        claim_id=claim_id,              # ✅ preserve claim_id
        status=status,
        transmission_id=None,
        raw_edi=reason or "",
        ack_type="ACK"
    )

    return {
        "submission_id": submission_id,
        "status": status,
        "reason": reason
    }


# -------------------------
# Denial from 835
# -------------------------
def record_denial(
    submission_id: str,
    denial_code: str,
    message: str
):
    submission = get_submission(submission_id)

    if not submission:
        raise ValueError(f"Submission not found: {submission_id}")

    # Update submission dict
    submission["status"] = "DENIED"
    submission["denial_code"] = denial_code
    submission["denial_reason"] = message

    # ✅ CORRECT CALL — match function signature
    save_submission(
        submission_id=submission["submission_id"],
        claim_id=submission.get("claim_id"),
        status="DENIED",
        transmission_id=submission.get("transmission_id"),
        raw_edi=submission.get("raw_edi", "")
    )

    return {
        "submission_id": submission["submission_id"],
        "claim_id": submission.get("claim_id"),
        "status": "DENIED",
        "denial_code": denial_code,
        "message": message
    }




# -------------------------
# Status lookup
# -------------------------
def fetch_status(submission_id: str):
    data = get_submission(submission_id)
    if not data:
        return {"error": "Submission not found"}
    return data


# -------------------------
# Submit claim from S3
# -------------------------
def submit_from_s3(payload: dict):
    """
    payload MUST contain:
    - claim_id
    - total_charge (used later in pipeline)
    """

    # 🔒 Validate claim_id early
    if not payload.get("claim_id"):
        raise ValueError("claim_id is required in payload")

    # 1. Generate submission_id if missing
    submission_id = payload.get("submission_id")
    if not submission_id:
        submission_id = f"AUTO-{uuid.uuid4().hex[:8]}"
        payload["submission_id"] = submission_id

    # 2. Save initial submission WITH claim_id
    save_submission(
        submission_id=submission_id,
        claim_id=payload["claim_id"],   # ✅ CRITICAL FIX
        status="SUBMITTED",
        transmission_id=None,
        raw_edi=""
    )

    return {
        "submission_id": submission_id,
        "status": "SUBMITTED"
    }

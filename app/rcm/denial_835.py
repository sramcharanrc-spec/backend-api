def parse_835(payload: dict) -> dict:
    if "submission_id" not in payload:
        raise ValueError("submission_id is required for denial")

    if "denial_code" not in payload:
        raise ValueError("denial_code is required for denial")

    return {
        "submission_id": payload["submission_id"],
        # claim_id will be resolved internally
        "denial_code": payload["denial_code"],
        "message": payload.get("message", "Denied by payer")
    }


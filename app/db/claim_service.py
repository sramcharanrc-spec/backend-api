from app.rcm.claim_store import save_claim, update_claim


def create_claim_record(claim):
    save_claim(
        claim.get("claim_id"),
        "RECEIVED",
        "INTAKE",
        claim
    )


def mark_claim_processing(claim_id):
    update_claim(claim_id, "PROCESSING")


def mark_claim_status(claim_id, status):
    update_claim(claim_id, status)
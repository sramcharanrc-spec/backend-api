from app.lambdas.claim_agent.claim_mapper import map_s3_json_to_claim
from app.lambdas.edi_agent.edi_837 import generate_edi_837
from app.rcm.submission import save_submission
from app.utils.s3_reader import load_latest_claim_from_s3

from fastapi import HTTPException
import uuid


def submit_claim(patient_id: str):
    # 1️⃣ Load generated claim JSON from S3
    try:
        raw_data = load_latest_claim_from_s3(
            bucket="healthcare-edi-output",
            patient_id=patient_id
        )
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"No generated claim found for patient_id={patient_id}"
        )

    # 2️⃣ Map JSON → internal claim model
    claim = map_s3_json_to_claim(raw_data)

    if "claim_id" not in claim:
        raise HTTPException(
            status_code=400,
            detail="claim_id missing in generated claim data"
        )

    # 3️⃣ Generate EDI 837
    edi_text = generate_edi_837(claim)

    # 4️⃣ Create submission ID
    submission_id = f"SUB-{uuid.uuid4().hex[:8]}"

    # 5️⃣ Save submission lifecycle
    save_submission(
        submission_id=submission_id,
        claim_id=claim["claim_id"],
        status="SUBMITTED",
        transmission_id=None,
        raw_edi=edi_text
    )

    # 6️⃣ Return clean response
    return {
        "submission_id": submission_id,
        "claim_id": claim["claim_id"],
        "status": "SUBMITTED"
    }

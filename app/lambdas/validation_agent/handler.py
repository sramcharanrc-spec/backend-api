from validation import validate_claim
from store import save_submission

def handler(event, context):
    submission_id = event["submission_id"]
    claim = event["claim"]

    result = validate_claim(claim)

    save_submission(
        submission_id=submission_id,
        status="VALIDATED" if result["valid"] else "FAILED",
        raw_edi=""
    )

    return {
        "submission_id": submission_id,
        "result": result
    }

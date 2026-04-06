import uuid
import datetime

FEEDBACK_DB = []

def store_feedback(claim_id, field, original, corrected):

    entry = {
        "id": str(uuid.uuid4()),
        "claim_id": claim_id,
        "field": field,
        "original": original,
        "corrected": corrected,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "embedding": None
    }

    FEEDBACK_DB.append(entry)

    return entry


def get_all_feedback():
    return FEEDBACK_DB
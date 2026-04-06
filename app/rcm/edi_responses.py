import random

def generate_999_ack():
    return {
        "ack_code": "999",
        "status": "ACCEPTED",
        "message": "EDI accepted at syntax level"
    }


def generate_277ca(submission_id: str, accepted=True):
    if accepted:
        return {
            "type": "277CA",
            "status": "ACCEPTED",
            "claim_id": submission_id
        }
    else:
        return {
            "type": "277CA",
            "status": "REJECTED",
            "error": "Missing required field"
        }


def generate_era_835(submission_id: str, amount: float):
    return {
        "type": "835",
        "claim_id": submission_id,
        "paid_amount": amount,
        "status": "PAID"
    }
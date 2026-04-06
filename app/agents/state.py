from typing import TypedDict

class ClaimState(TypedDict):
    claim_id: str
    edi_file: str
    submission_status: str
    ack_status: str
    denial_status: str
    payment_status: str
    claim: object
    status: str
    
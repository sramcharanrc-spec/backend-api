# ehr_pipeline/app/events/event_types.py

class EventType:
    CLAIM_CREATED = "ClaimCreated"
    CLAIM_VALIDATED = "ClaimValidated"
    CLAIM_SUBMITTED = "ClaimSubmitted"
    CLAIM_DENIED = "ClaimDenied"
    CLAIM_PAID = "ClaimPaid"
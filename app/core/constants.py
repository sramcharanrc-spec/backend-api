# ehr_pipeline/app/core/constants.py


from enum import Enum


class ClaimStatusEnum(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    DENIED = "denied"
    CORRECTED = "corrected"
    PAID = "paid"
    FAILED = "failed"

    
MAX_RETRY_ATTEMPTS = 3
DEFAULT_PAYER = "MEDICARE"
CLEAN_CLAIM_THRESHOLD = 0.9
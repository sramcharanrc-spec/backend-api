from enum import Enum


class ClaimStatusEnum(str, Enum):
    CREATED = "created"
    GENERATED = "generated"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PENDING_CLEARINGHOUSE = "PENDING_CLEARINGHOUSE"
    ACCEPTED = "ACCEPTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESUBMITTED = "RESUBMITTED"
    COMPLETED = "COMPLETED"
    ACK_RECEIVED = "ack_received"
    DENIED = "denied"
    CORRECTED = "corrected"
    PAID = "paid"
    FAILED = "failed"
    VALIDATION_FAILED = "VALIDATION_FAILED"

from enum import Enum


class ClaimStatusEnum(str, Enum):
    CREATED = "created"
    GENERATED = "generated"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    ACK_RECEIVED = "ack_received"
    DENIED = "denied"
    CORRECTED = "corrected"
    PAID = "paid"
    FAILED = "failed"
# ehr_pipeline/app/core/state_machine.py

from enum import Enum


class ClaimStatus(str, Enum):
    CREATED = "created"
    GENERATED = "generated"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    ACK_RECEIVED = "ack_received"
    DENIED = "denied"
    CORRECTED = "corrected"
    PAID = "paid"
    FAILED = "failed"


class PipelineState(str, Enum):
    OCR = "OCR"
    VALIDATION = "VALIDATION"
    COMPLIANCE = "COMPLIANCE"
    SUBMISSION = "SUBMISSION"
    CLEARINGHOUSE = "CLEARINGHOUSE"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PAUSED = "PAUSED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RESUMED = "RESUMED"
    LEARNING = "LEARNING"
    ANALYTICS = "ANALYTICS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


PIPELINE_STAGES = (
    "OCR",
    "VALIDATION",
    "COMPLIANCE",
    "SUBMISSION",
    "CLEARINGHOUSE",
    "LEARNING",
    "ANALYTICS",
    "COMPLETED",
)

WAITING_STATES = {
    PipelineState.WAITING_FOR_APPROVAL.value,
    "PENDING_CLEARINGHOUSE",
    "CLEARINGHOUSE_PENDING",
    "WAITING_APPROVAL",
}

RESUMED_STATES = {
    PipelineState.RESUMED.value,
    PipelineState.LEARNING.value,
    PipelineState.ANALYTICS.value,
}

FINAL_PIPELINE_STATES = {
    PipelineState.COMPLETED.value,
    "PAID",
    "FINALIZED",
    "CLOSED",
    "SUCCESS",
    "ARCHIVED",
}


def normalize_state(value: object, default: str = "PENDING") -> str:
    return str(value or default).strip().upper().replace("-", "_").replace(" ", "_")


def is_waiting_for_approval(value: object) -> bool:
    return normalize_state(value) in WAITING_STATES


def is_final_pipeline_state(value: object) -> bool:
    return normalize_state(value) in FINAL_PIPELINE_STATES


def waiting_stage_statuses() -> dict:
    return {
        "OCR": "COMPLETED",
        "VALIDATION": "COMPLETED",
        "COMPLIANCE": "COMPLETED",
        "SUBMISSION": "COMPLETED",
        "CLEARINGHOUSE": "WAITING_APPROVAL",
        "LEARNING": "PENDING",
        "ANALYTICS": "PENDING",
        "COMPLETED": "PENDING",
    }

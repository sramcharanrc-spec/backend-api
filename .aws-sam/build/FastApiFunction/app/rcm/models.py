from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import List, Optional

class ClaimStatus(str, Enum):
    VALIDATION_FAILED = "validation_failed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

@dataclass
class ClaimLine:
    cpt: str
    modifier: Optional[str] = None
    charge_amount: float = 0.0

@dataclass
class Claim:
    id: str
    patient_id: str
    patient_name: str
    payer_id: str
    provider_npi: str
    diagnosis_codes: List[str]
    service_date: date
    place_of_service: str
    lines: List[ClaimLine] = field(default_factory=list)
    status: ClaimStatus = ClaimStatus.ACCEPTED

@dataclass
class Submission:
    id: str
    claim_id: str
    created_at: datetime
    status: ClaimStatus
    raw_edi: str
    denial_reason: Optional[str] = None

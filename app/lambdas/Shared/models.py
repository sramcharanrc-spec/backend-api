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


# --- Pydantic models for incoming (flat/CMS1500-style) payloads ---
# These are used for validation/mapping (ClaimIn -> EDA -> Claim dataclass)

from pydantic import BaseModel, validator, Field

class Procedure(BaseModel):
    code: str
    desc: Optional[str] = None
    charge: Optional[float] = None
    mod: Optional[str] = None
    pointer: Optional[int] = None

class ClaimIn(BaseModel):
    status: Optional[str] = None
    claim_eligible: Optional[bool] = None
    form_type: Optional[str] = None
    encounter_type: Optional[str] = None

    pt_name: Optional[str] = None
    pt_street: Optional[str] = None
    pt_city: Optional[str] = None
    pt_state: Optional[str] = None
    pt_zip: Optional[str] = None
    sex: Optional[str] = None
    birth_mm: Optional[str] = None
    birth_dd: Optional[str] = None
    birth_yy: Optional[str] = None

    insurance_name: Optional[str] = None
    payer_type: Optional[str] = None
    insurance_id: Optional[str] = None

    cpt1: Optional[str] = None
    cpt2: Optional[str] = None
    cpt3: Optional[str] = None
    cpt4: Optional[str] = None
    cpt1_desc: Optional[str] = None
    cpt2_desc: Optional[str] = None
    cpt3_desc: Optional[str] = None
    cpt4_desc: Optional[str] = None

    cpt1_charge: Optional[float] = None
    cpt2_charge: Optional[float] = None
    cpt3_charge: Optional[float] = None
    cpt4_charge: Optional[float] = None

    total_charge: Optional[float] = None
    billing_provider_npi: Optional[str] = None
    service_facility_name: Optional[str] = None

    # additional optional fields you may receive
    claim_id: Optional[str] = None
    service_date: Optional[str] = None
    service_from_mm: Optional[str] = None
    service_from_dd: Optional[str] = None
    service_from_yy: Optional[str] = None
    units: Optional[int] = None
    mod1: Optional[str] = None
    # ...add anything else you expect

    @validator("cpt1_charge", "cpt2_charge", "cpt3_charge", "cpt4_charge", "total_charge", pre=True)
    def parse_money(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        # remove common formatting
        s = s.replace(",", "").replace("$", "")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"Unable to parse money value: {v!r}")
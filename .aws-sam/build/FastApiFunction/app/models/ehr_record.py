# ehr_pipeline/app/models/ehr_record.py
from typing import List, Optional
from pydantic import BaseModel

class EHRRecord(BaseModel):
    id: str
    patient_id: Optional[str] = None
    chief_complaint: Optional[str] = None
    assessment: Optional[str] = None
    notes: Optional[str] = None
    # raw row for debugging
    raw: dict

class ClaimLine(BaseModel):
    cpt: str
    description: str
    quantity: int = 1
    unit_price: float = 0.0
    line_total: float = 0.0

class Claim(BaseModel):
    claim_id: str
    patient_id: Optional[str] = None
    icd_codes: List[str] = []
    cpt_lines: List[ClaimLine] = []
    total_amount: float = 0.0

class CompareResult(BaseModel):
    baseline: Claim
    coded: Claim
    deltas: dict

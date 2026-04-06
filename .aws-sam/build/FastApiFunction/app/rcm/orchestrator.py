from datetime import date
from typing import Dict
from .models import Claim, ClaimLine, ClaimStatus
from .edi_837 import build_837
from .clearinghouse_client import submit_edi

def _build_claim_from_eda(eda: Dict) -> Claim:
    p = eda["patient"]
    prov = eda["provider"]
    payer = eda["payer"]

    lines = [
        ClaimLine(
            cpt=l["cpt"],
            modifier=l.get("modifier"),
            charge_amount=l.get("charge_amount", 0.0),
        )
        for l in eda.get("procedure_lines", [])
    ]

    return Claim(
        id=eda["claim_id"],
        patient_id=p["id"],
        patient_name=p["name"],
        payer_id=payer["id"],
        provider_npi=prov["npi"],
        diagnosis_codes=eda.get("diagnosis_codes", []),
        service_date=date.fromisoformat(eda["service_date"]),
        place_of_service=eda.get("place_of_service", "11"),
        lines=lines,
    )

def submit_claim_from_eda(eda: Dict):
    claim = _build_claim_from_eda(eda)

    if not claim.diagnosis_codes:
        return {
            "status": ClaimStatus.VALIDATION_FAILED.value,
            "errors": ["Missing ICD-10 diagnosis code"],
            "claim_id": claim.id,
        }

    edi_837 = build_837(claim, test=True)
    submission = submit_edi(edi_837, claim)

    return {
        "claim_id": claim.id,
        "submission_id": submission.id,
        "status": submission.status.value,
        "denial_reason": submission.denial_reason,
    }

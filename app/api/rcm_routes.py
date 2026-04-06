from fastapi import APIRouter
from app.orchestrator.rcm_orchestrator import RCMOrchestrator
from app.models.claim_model import Claim
from app.models.enums import ClaimStatusEnum

router = APIRouter()
orchestrator = RCMOrchestrator()

@router.post("/claims/process")
async def process_claim(claim_data: dict):

    claim = Claim(
        id=claim_data["id"],
        patient_id=claim_data["patient_id"],
        payer_id=claim_data["payer_id"],
        cpt_codes=claim_data["cpt_codes"],
        icd_codes=claim_data["icd_codes"],
        status=ClaimStatusEnum.CREATED
    )

    result = await orchestrator.process(claim)

    return {
        "id": result.id,
        "status": result.status.value,
        "paid_amount": result.paid_amount
    }
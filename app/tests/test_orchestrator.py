import pytest
from app.orchestrator.rcm_orchestrator import RCMOrchestrator
from app.models.claim_model import Claim
from app.models.enums import ClaimStatusEnum


class FakeBedrock:
    async def invoke(self, prompt):
        return "Correct CPT to 99214"
@pytest.mark.asyncio
async def test_full_rcm_flow():

    claim = Claim(
        id="C100",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=["99213"],
        icd_codes=["Z00.00"],
        status=ClaimStatusEnum.CREATED
    )

    orchestrator = RCMOrchestrator()

    # Inject mock into denial agent
    orchestrator.denial.llm = FakeBedrock()

    result = await orchestrator.process(claim)

    assert result.status in [
        ClaimStatusEnum.PAID,
        ClaimStatusEnum.DENIED,
        ClaimStatusEnum.ACK_RECEIVED
    ]
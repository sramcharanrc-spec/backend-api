import pytest
from app.core.retry_handler import execute_with_retry
from app.core.state_machine import ClaimStatus
from app.models.claim_model import Claim


class FailingAgent:
    async def run(self, claim):
        raise Exception("Test failure")


@pytest.mark.asyncio
async def test_retry_exceeds_limit():

    claim = Claim(
        id="C5",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=["99213"],
        icd_codes=["Z00.00"],
        status=ClaimStatus.CREATED
    )

    agent = FailingAgent()

    for _ in range(3):
        try:
            await execute_with_retry(agent, claim)
        except:
            pass

    assert claim.retry_count >= 1
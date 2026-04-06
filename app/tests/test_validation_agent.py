import pytest
import asyncio
from app.agents.validation.validation_agent import ValidationAgent
from app.models.claim_model import Claim
from app.models.enums import ClaimStatusEnum


@pytest.mark.asyncio
async def test_validation_success():

    claim = Claim(
        id="C2",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=["99213"],
        icd_codes=["Z00.00"],
        status=ClaimStatusEnum.CREATED
    )

    agent = ValidationAgent()
    result = await agent.run(claim)

    assert result.status == ClaimStatusEnum.VALIDATED


@pytest.mark.asyncio
async def test_validation_fail():

    claim = Claim(
        id="C3",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=[],
        icd_codes=[],
        status=ClaimStatusEnum.CREATED
    )

    agent = ValidationAgent()
    result = await agent.run(claim)

    assert result.status == ClaimStatusEnum.FAILED
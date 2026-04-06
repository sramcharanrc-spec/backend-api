import pytest
from app.models.claim_model import Claim
from app.models.enums import ClaimStatusEnum


def test_claim_model_creation():

    claim = Claim(
        id="C1",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=["99213"],
        icd_codes=["Z00.00"],
        status=ClaimStatusEnum.CREATED
    )

    assert claim.status == ClaimStatusEnum.CREATED
    assert claim.retry_count == 0
    assert claim.is_deleted is False
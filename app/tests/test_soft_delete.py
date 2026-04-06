from app.models.claim_model import Claim

def test_soft_delete():

    claim = Claim(
        id="C6",
        patient_id="P1",
        payer_id="MED1",
        cpt_codes=["99213"],
        icd_codes=["Z00.00"],
        status="created"
    )

    claim.soft_delete()

    assert claim.is_deleted is True
    assert claim.deleted_at is not None
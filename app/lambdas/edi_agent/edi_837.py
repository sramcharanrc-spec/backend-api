from app.lambdas.etl_agent.s3_client import load_latest_claim_from_s3
import uuid



def generate_edi_837(claim: dict) -> str:
    claim_id = claim["claim_id"]

    edi = f"""
ISA*00*          *00*          *ZZ*AGENTICAI     *ZZ*PAYER        *250101*1200*^*00501*000000001*0*T*:
GS*HC*AGENTICAI*PAYER*20250101*1200*1*X*005010X222A1
ST*837*0001*005010X222A1
BHT*0019*00*{claim_id}*20250101*1200*CH

NM1*41*2*AGENTICAI*****46*12345
NM1*40*2*PAYER*****

NM1*QC*1*{claim["patient"]["name"].split()[-1]}*{claim["patient"]["name"].split()[0]}****
NM1*85*2*{claim["provider"]["name"]}*****XX*{claim["provider"]["npi"]}
"""

    for svc in claim["services"]:
        edi += f"SV1*HC:{svc['cpt']}*{svc['charge']}*UN*{svc['units']}***1\n"

    edi += """
SE*10*0001
GE*1*1
IEA*1*000000001
"""

    return edi.strip()


def submit_claim_to_edi(claim_id: str):

    # 🔥 LOAD CLAIM JSON FROM S3
    claim = load_latest_claim_from_s3(claim_id)

    if not claim:
        return {
            "status": "FAILED",
            "errors": ["Claim not found in S3"]
        }

    # 🔁 JSON → EDI
    edi_text = generate_edi_837(claim)

    submission_id = f"SUB-{uuid.uuid4().hex[:8]}"

    save_submission(
        submission_id=submission_id,
        claim_id=claim_id,
        status="SUBMITTED",
        transmission_id=None,
        raw_edi=edi_text
    )

    return {
        "submission_id": submission_id,
        "status": "SUBMITTED"
    }

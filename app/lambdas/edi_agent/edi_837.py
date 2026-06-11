from __future__ import annotations


def generate_edi_837(claim: dict) -> str:
    claim_id = claim.get("claim_id", "UNKNOWN")
    total = claim.get("total_charge", 0)
    patient = claim.get("patient", {}) if isinstance(claim.get("patient"), dict) else {}
    provider = claim.get("provider", {}) if isinstance(claim.get("provider"), dict) else {}

    return "~".join(
        [
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *260505*0000*^*00501*000000001*0*T*:~",
            f"NM1*QC*1*{patient.get('name', 'UNKNOWN')}****MI*{claim_id}~",
            f"NM1*82*2*{provider.get('name', 'PROVIDER')}*****XX*{provider.get('npi', '0000000000')}~",
            f"CLM*{claim_id}*{total}***11:B:1*Y*A*Y*Y~",
            "SE*4*0001~",
        ]
    )

from datetime import datetime
from .models import Claim

def build_837(claim: Claim, test: bool = True) -> str:
    now = datetime.utcnow()
    isa_ctrl = "000000001"
    gs_ctrl = "1"
    st_ctrl = "0001"
    ti = "T" if test else "P"

    segs = []

    segs.append(
        f"ISA*00*          *00*          *ZZ*SENDERID*ZZ*RECEIVERID*"
        f"{now:%y%m%d}*{now:%H%M}*^*00501*{isa_ctrl}*0*{ti}*:~"
    )
    segs.append(
        f"GS*HC*SENDERID*RECEIVERID*{now:%Y%m%d}*{now:%H%M}*{gs_ctrl}*X*005010X222A1~"
    )
    segs.append(f"ST*837*{st_ctrl}*005010X222A1~")

    segs.append("NM1*85*2*DEMO CLINIC*****XX*1234567893~")
    segs.append("N3*123 MAIN ST~")
    segs.append("N4*ANYTOWN*CA*90001~")

    segs.append(f"NM1*IL*1*{claim.patient_name}****MI*{claim.patient_id}~")

    if claim.diagnosis_codes:
        segs.append(f"HI*ABK:{claim.diagnosis_codes[0]}~")

    total = sum(l.charge_amount for l in claim.lines)
    segs.append(f"CLM*{claim.id}*{total:.2f}***11:{claim.place_of_service}:1*Y*A*Y*Y~")

    for idx, line in enumerate(claim.lines, start=1):
        segs.append(f"LX*{idx}~")
        segs.append(f"SV1*HC:{line.cpt}*{line.charge_amount:.2f}*UN*1***1~")

    segs.append(f"SE*{len(segs)+1}*{st_ctrl}~")
    segs.append(f"GE*1*{gs_ctrl}~")
    segs.append(f"IEA*1*{isa_ctrl}~")

    return "\n".join(segs)

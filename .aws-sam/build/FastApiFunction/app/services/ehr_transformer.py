# ehr_pipeline/app/services/ehr_transformer.py
from typing import List
from ..models.ehr_record import Claim, ClaimLine, EHRRecord
from .ehr_extractor import extract_icd_and_cpt
from .catalogs import get_icd, get_cpt

def build_claim(record: EHRRecord, include_codes: bool) -> Claim:
    claim_id = f"CLM-{record.id}"
    patient_id = record.patient_id

    # Baseline claim (no codes): assume visit if text implies it.
    if not include_codes:
        text = " ".join([record.chief_complaint or "", record.assessment or "", record.notes or ""]).lower()
        has_visit = any(w in text for w in ["visit", "consult", "checkup", "follow-up"])
        base_lines: List[ClaimLine] = []
        if has_visit:
            # Try to enrich 99213 from CPT master
            cpt = get_cpt("99213")
            price = cpt["fee"] if cpt and "fee" in cpt else 95.0
            desc  = cpt["description"] if cpt else "Office/outpatient visit est"
            base_lines.append(ClaimLine(cpt="99213", description=desc, quantity=1,
                                        unit_price=price, line_total=price))
        return Claim(
            claim_id=claim_id, patient_id=patient_id,
            icd_codes=[],
            cpt_lines=base_lines,
            total_amount=sum(x.line_total for x in base_lines)
        )

    # Coded claim using extraction + catalogs
    icd_codes, cpt_codes = extract_icd_and_cpt([
        record.chief_complaint or "", record.assessment or "", record.notes or ""
    ])

    # Enrich ICDs from master (keep only valid ones)
    enriched_icds: List[str] = []
    for icd in icd_codes:
        icd_row = get_icd(icd)
        if icd_row:
            enriched_icds.append(icd_row["code"])
        # else: drop unknown code

    # Enrich CPTs to claim lines from master
    cpt_lines: List[ClaimLine] = []
    for cpt in cpt_codes:
        row = get_cpt(cpt)
        if not row:
            # skip unknown CPTs (or set default)
            continue
        price = float(row.get("fee", 0.0) or 0.0)
        desc  = row.get("description", "CPT Service")
        cpt_lines.append(ClaimLine(
            cpt=row["code"], description=desc, quantity=1, unit_price=price, line_total=price
        ))

    total = sum(l.line_total for l in cpt_lines)

    return Claim(
        claim_id=claim_id, patient_id=patient_id,
        icd_codes=enriched_icds,
        cpt_lines=cpt_lines,
        total_amount=total
    )

def compare_claims(record: EHRRecord):
    baseline = build_claim(record, include_codes=False)
    coded = build_claim(record, include_codes=True)
    delta_amount = coded.total_amount - baseline.total_amount
    deltas = {
        "amount_delta": delta_amount,
        "icd_added": [c for c in coded.icd_codes if c not in baseline.icd_codes],
        "cpt_added": [l.cpt for l in coded.cpt_lines if l.cpt not in [b.cpt for b in baseline.cpt_lines]],
        "baseline_total": baseline.total_amount,
        "coded_total": coded.total_amount,
    }
    return baseline, coded, deltas

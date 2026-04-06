# ehr_pipeline/app/services/publisher.py
from typing import List
from ..models.ehr_record import Claim, EHRRecord

def summarize_for_frontend(records: List[EHRRecord], claims_coded: List[Claim]):
    """
    Return a compact payload for dashboards: counts, totals, top codes.
    """
    count_records = len(records)
    total_amount = sum(c.total_amount for c in claims_coded)
    top_cpt = {}
    for c in claims_coded:
        for line in c.cpt_lines:
            top_cpt[line.cpt] = top_cpt.get(line.cpt, 0) + 1

    top_cpt_sorted = sorted(top_cpt.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "records": count_records,
        "coded_claims_total": total_amount,
        "top_cpt": top_cpt_sorted[:10],
    }

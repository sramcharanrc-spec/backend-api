# ehr_pipeline/app/router_claims.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List, Dict, Any

from .services.ehr_loader import load_csv_to_records
from .services.code_resolver import resolve_codes_for_row, decide_e_claim
from .services.ehr_transformer import compare_claims  # optional: adds baseline/coded totals

router = APIRouter()

@router.post("/table")
async def table_view(
    note_fields: str = Query(default="assessment,notes,chief_complaint"),
    file: UploadFile = File(...)
):
    """
    Upload EHR file (CSV/XLSX) and get flat rows for the UI:
      patient_id, icd_code, icd_desc, cpt_code, cpt_desc, e_claim
    Also includes baseline/coded totals and amount_delta for comparison.
    """
    try:
        raw = await file.read()
        nf_list: List[str] = [f.strip() for f in note_fields.split(",") if f.strip()]
        records = load_csv_to_records(raw, nf_list, filename=file.filename)

        rows: List[Dict[str, Any]] = []
        for rec in records:
            # infer/enrich codes for this row
            icds, cpts = resolve_codes_for_row(rec.raw)
            eclaim = decide_e_claim(rec.raw, icds, cpts)

            # optional: compute baseline vs coded using your transformer
            baseline, coded, deltas = compare_claims(rec)

            # ensure at least one output row per record
            if not icds:
                icds = [{"code": "", "description": ""}]
            if not cpts:
                cpts = [{"code": "", "description": "", "fee": 0.0}]

            for icd in icds:
                for cpt in cpts:
                    rows.append({
                        "patient_id": rec.patient_id or rec.id,
                        "icd_code": icd.get("code", ""),
                        "icd_desc": icd.get("description", ""),
                        "cpt_code": cpt.get("code", ""),
                        "cpt_desc": cpt.get("description", ""),
                        "e_claim": eclaim,
                        # comparison fields for UI (optional but useful)
                        "baseline_total": deltas["baseline_total"],
                        "coded_total": deltas["coded_total"],
                        "amount_delta": deltas["amount_delta"],
                    })

        return {"ok": True, "count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
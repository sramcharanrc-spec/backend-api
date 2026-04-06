# ehr_pipeline/app/router_coder.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List
from .services.ehr_validator import validate_columns
from .services.ehr_loader import load_csv_to_records
from .services.ehr_transformer import compare_claims
from .services.publisher import summarize_for_frontend
from .services.catalogs import reload_catalogs
import pandas as pd, io

router = APIRouter()

@router.post("/map-csv")
async def map_csv(
    note_fields: str = Query(default="assessment,notes,chief_complaint"),
    file: UploadFile = File(...)
):
    try:
        raw = await file.read()
        text = raw.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(text))
        cols = list(df.columns)
        nf_list: List[str] = [f.strip() for f in note_fields.split(",") if f.strip()]
        validate_columns(cols, nf_list)

        records = load_csv_to_records(raw, nf_list, filename=file.filename)

        results = []
        coded_claims = []
        for rec in records:
            baseline, coded, deltas = compare_claims(rec)
            coded_claims.append(coded)
            results.append({
                "record_id": rec.id,
                "patient_id": rec.patient_id,
                "baseline": baseline.dict(),
                "coded": coded.dict(),
                "deltas": deltas,
            })

        summary = summarize_for_frontend(records, coded_claims)
        return {"ok": True, "results": results, "summary": summary}

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reload-catalogs")
def reload():
    try:
        reload_catalogs()
        return {"ok": True, "message": "ICD and CPT catalogs reloaded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

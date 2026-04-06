# ehr_pipeline/app/router_icd.py
from fastapi import APIRouter
from .icd.icd_dict import ICD_KEYWORDS, CPT_KEYWORDS

router = APIRouter()

@router.get("/keywords")
def keywords():
    return {"icd_keywords": ICD_KEYWORDS, "cpt_keywords": CPT_KEYWORDS}

# ehr_pipeline/app/router_rcm.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/ping")
def ping():
    return {"rcm": "ok"}

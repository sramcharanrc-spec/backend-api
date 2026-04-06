from fastapi import APIRouter
from app.services.audit_service import get_audit_logs

router = APIRouter()

@router.get("/audit")
def fetch_all():
    return get_audit_logs()

@router.get("/audit/{claim_id}")
def fetch_by_claim(claim_id: str):
    return get_audit_logs(claim_id)
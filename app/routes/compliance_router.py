from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.compliance_schema import ComplianceAuditResponse
from app.services.compliance_service import ComplianceService
from app.utils.serializer import serialize_sqlalchemy_list
from typing import List

router = APIRouter()

@router.get("/compliance", response_model=List[ComplianceAuditResponse])
async def get_compliance_audits(db: Session = Depends(get_db)):
    service = ComplianceService(db)
    audits = service.get_all_audits()
    return serialize_sqlalchemy_list(audits)

@router.get("/compliance/{claim_id}", response_model=List[ComplianceAuditResponse])
async def get_compliance_by_claim(claim_id: str, db: Session = Depends(get_db)):
    service = ComplianceService(db)
    audits = service.get_audits_by_claim(claim_id)
    return serialize_sqlalchemy_list(audits)

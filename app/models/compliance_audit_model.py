from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from app.models.base import Base
from datetime import datetime

class ComplianceAudit(Base):
    __tablename__ = "compliance_audit"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    submission_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String)  # COMPLIANT, NON_COMPLIANT, MANUAL_REVIEW
    issues = Column(JSON)
    audit_details = Column(JSON)
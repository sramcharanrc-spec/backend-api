from datetime import datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def default_sla_due():
    return datetime.utcnow() + timedelta(hours=4)


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, unique=True, nullable=False, index=True)
    claim_id = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    case_type = Column(String, default="HITL")
    status = Column(String, default="NEW", index=True)
    priority = Column(String, default="MEDIUM", index=True)
    assigned_role = Column(String, default="MA Team", index=True)
    assigned_team = Column(String, default="MA Team", index=True)
    assigned_to = Column(String, nullable=True, index=True)
    escalation_level = Column(Integer, default=0)
    sla_due_at = Column(DateTime, default=default_sla_due, index=True)
    sla_deadline = Column(DateTime, default=default_sla_due, index=True)
    sla_status = Column(String, default="ON_TRACK")
    next_stage = Column(String, nullable=True, index=True)
    denial_reason = Column(Text, nullable=True)
    ai_suggestion = Column(Text, nullable=True)
    risk_score = Column(Float, default=0)
    confidence = Column(Float, default=0)
    corrected_fields = Column(JSON, default=list)
    template_name = Column(String, nullable=True)
    confidence_score = Column(Float, default=0)
    extraction_quality = Column(String, default="unknown")
    metadata_json = Column(JSON, default=dict)
    created_by = Column(String, default="SYSTEM")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    comments = relationship("CaseComment", back_populates="case", cascade="all, delete-orphan")
    assignments = relationship("CaseAssignment", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("CaseAuditLog", back_populates="case", cascade="all, delete-orphan")
    escalations = relationship("CaseEscalation", back_populates="case", cascade="all, delete-orphan")


class CaseComment(Base):
    __tablename__ = "case_comments"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    author = Column(String, default="SYSTEM")
    role = Column(String, default="Admin")
    comment = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    case = relationship("Case", back_populates="comments")


class CaseAssignment(Base):
    __tablename__ = "case_assignments"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    assigned_role = Column(String, nullable=False)
    assigned_to = Column(String, nullable=True)
    assigned_by = Column(String, default="SYSTEM")
    reason = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    case = relationship("Case", back_populates="assignments")


class CaseAuditLog(Base):
    __tablename__ = "case_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    actor = Column(String, default="SYSTEM")
    action = Column(String, nullable=False, index=True)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    case = relationship("Case", back_populates="audit_logs")


class CaseEscalation(Base):
    __tablename__ = "case_escalations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    level = Column(Integer, default=1)
    from_role = Column(String, nullable=True)
    to_role = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String, default="OPEN", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)

    case = relationship("Case", back_populates="escalations")

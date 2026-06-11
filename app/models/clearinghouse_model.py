from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text

from app.models.base import Base


class ClearinghouseEvent(Base):
    __tablename__ = "clearinghouse_events"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    action = Column(String, index=True, nullable=False)
    reviewer = Column(String, default="SYSTEM")
    status = Column(String, index=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SubmissionHistory(Base):
    __tablename__ = "submission_history"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    submission_id = Column(String, index=True)
    transmission_id = Column(String, index=True)
    status = Column(String, index=True)
    reviewer = Column(String, default="SYSTEM")
    attempt = Column(Integer, default=1)
    raw_edi = Column(Text, nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DenialHistory(Base):
    __tablename__ = "denial_history"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    denial_reason = Column(Text)
    risk_score = Column(Float, default=0)
    confidence = Column(Float, default=0)
    suggestions = Column(JSON, default=list)
    auto_fix_available = Column(String, default="false")
    reviewer = Column(String, default="SYSTEM")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PaymentHistory(Base):
    __tablename__ = "payment_history"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    payment_id = Column(String, index=True)
    status = Column(String, index=True)
    paid_amount = Column(Float, default=0)
    reviewer = Column(String, default="SYSTEM")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

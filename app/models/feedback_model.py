from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float
from app.models.base import Base
from datetime import datetime

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    submission_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    outcome = Column(String)
    denial_reason = Column(Text)
    validation_corrections = Column(JSON)
    hitl_modifications = Column(JSON)
    payment_outcome = Column(String)
    risk_score = Column(Float)
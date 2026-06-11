from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from app.models.base import Base


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    field = Column(String, index=True)
    current_value = Column(JSON)
    suggested_value = Column(JSON)
    confidence = Column(Float, default=0.0)
    reason = Column(String)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)


class CorrectionHistory(Base):
    __tablename__ = "correction_history"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    field = Column(String)
    previous_value = Column(JSON)
    corrected_value = Column(JSON)
    source = Column(String, default="AI")
    accepted = Column(String, default="PENDING")
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class RepairLog(Base):
    __tablename__ = "repair_logs"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    status = Column(String)
    retry_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtractionConfidence(Base):
    __tablename__ = "extraction_confidence"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    field = Column(String, index=True)
    value = Column(String)
    confidence = Column(Float, default=0.0)
    source = Column(String, default="textract")
    form_type = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TextractEntity(Base):
    __tablename__ = "textract_entities"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    entity_type = Column(String, index=True)
    text = Column(String)
    confidence = Column(Float, default=0.0)
    page = Column(Integer, default=1)
    raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppealHistory(Base):
    __tablename__ = "appeal_history"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    payer = Column(String)
    denial_code = Column(String)
    denial_reason = Column(String)
    appeal_text = Column(String)
    status = Column(String, default="DRAFT")
    retry_probability = Column(Float, default=0.0)
    analysis = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

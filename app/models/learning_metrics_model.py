from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from app.models.base import Base
from datetime import datetime

class LearningMetrics(Base):
    __tablename__ = "learning_metrics"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    denial_patterns = Column(JSON)
    correction_history = Column(JSON)
    confidence_trends = Column(JSON)
    improvement_signals = Column(JSON)
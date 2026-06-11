from sqlalchemy import Column, Integer, String, DateTime, Text
from app.models.base import Base
from datetime import datetime

class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True)
    agent = Column(String)
    status = Column(String)  # running, completed, failed
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(Text)
    execution_time = Column(Integer)  # in milliseconds
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base


class ClaimHistory(Base):
    __tablename__ = "claim_history"

    id = Column(String, primary_key=True)
    claim_id = Column(String, ForeignKey("claims.id"), nullable=False)
    previous_status = Column(String)
    new_status = Column(String)
    changed_by = Column(String)  # system / user id
    timestamp = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim")
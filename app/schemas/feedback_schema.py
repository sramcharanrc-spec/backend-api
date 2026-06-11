from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class FeedbackResponse(BaseModel):
    id: int
    claim_id: Optional[str] = None
    submission_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    outcome: Optional[str] = None
    denial_reason: Optional[str] = None
    validation_corrections: Optional[Any] = None
    hitl_modifications: Optional[Any] = None
    payment_outcome: Optional[str] = None
    risk_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

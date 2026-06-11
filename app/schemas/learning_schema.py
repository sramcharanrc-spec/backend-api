from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class LearningMetricResponse(BaseModel):
    id: int
    claim_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    denial_patterns: Optional[Any] = None
    correction_history: Optional[Any] = None
    confidence_trends: Optional[Any] = None
    improvement_signals: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PipelineEventResponse(BaseModel):
    id: int
    claim_id: Optional[str] = None
    agent: Optional[str] = None
    status: Optional[str] = None
    timestamp: Optional[datetime] = None
    message: Optional[str] = None
    execution_time: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

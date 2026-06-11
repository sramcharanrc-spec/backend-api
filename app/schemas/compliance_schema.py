from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ComplianceAuditResponse(BaseModel):
    id: int
    claim_id: Optional[str] = None
    submission_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    status: Optional[str] = None
    issues: Optional[Any] = None
    audit_details: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


CASE_STATES = {
    "NEW",
    "IN_REVIEW",
    "COMPLIANCE_REVIEW",
    "LEGAL_REVIEW",
    "APPROVED",
    "REJECTED",
    "ESCALATED",
    "CLOSED",
}

ROUTING_ROLES = {"MA Team", "HEOR Team", "Legal Team", "Compliance Team", "Admin"}


class CaseCreate(BaseModel):
    claim_id: Optional[str] = None
    title: str = "HITL Review Case"
    description: Optional[str] = None
    case_type: str = "HITL"
    priority: str = "MEDIUM"
    assigned_role: str = "MA Team"
    assigned_team: Optional[str] = None
    assigned_to: Optional[str] = None
    next_stage: Optional[str] = None
    created_by: str = "SYSTEM"
    denial_reason: Optional[str] = None
    ai_suggestion: Optional[str] = None
    risk_score: float = 0
    confidence: float = 0
    template_name: Optional[str] = None
    confidence_score: float = 0
    extraction_quality: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StatusUpdate(BaseModel):
    status: str
    actor: str = "SYSTEM"
    reason: Optional[str] = None


class AssignmentUpdate(BaseModel):
    assigned_role: str
    assigned_to: Optional[str] = None
    assigned_by: str = "SYSTEM"
    reason: Optional[str] = None


class CommentCreate(BaseModel):
    author: str = "SYSTEM"
    role: str = "Admin"
    comment: str


class CaseOut(BaseModel):
    case_id: str
    claim_id: Optional[str]
    title: str
    description: Optional[str]
    case_type: str
    status: str
    priority: str
    assigned_role: str
    assigned_team: Optional[str] = None
    assigned_to: Optional[str]
    escalation_level: int
    sla_due_at: Optional[datetime]
    sla_deadline: Optional[datetime] = None
    sla_status: str
    next_stage: Optional[str] = None
    denial_reason: Optional[str]
    ai_suggestion: Optional[str]
    risk_score: float
    confidence: float
    corrected_fields: List[Dict[str, Any]] = Field(default_factory=list)
    template_name: Optional[str]
    confidence_score: float
    extraction_quality: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    assignments: List[Dict[str, Any]] = Field(default_factory=list)
    audit_logs: List[Dict[str, Any]] = Field(default_factory=list)
    escalations: List[Dict[str, Any]] = Field(default_factory=list)

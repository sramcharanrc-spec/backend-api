import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.case_management.models.case_models import (
    Case,
    CaseAssignment,
    CaseAuditLog,
    CaseComment,
    CaseEscalation,
)
from app.case_management.schemas import CASE_STATES, ROUTING_ROLES, AssignmentUpdate, CaseCreate


ROLE_SLA_HOURS = {
    "MA Team": 4,
    "HEOR Team": 8,
    "Compliance Team": 6,
    "Legal Team": 12,
    "Admin": 24,
}

ESCALATION_ROUTE = {
    "MA Team": "HEOR Team",
    "HEOR Team": "Compliance Team",
    "Compliance Team": "Legal Team",
    "Legal Team": "Admin",
    "Admin": "Admin",
}

ROLE_ALIASES = {
    "MA": "MA Team",
    "MA_TEAM": "MA Team",
    "MEDICAL_ASSISTANT": "MA Team",
    "MEDICAL_ASSISTANT_TEAM": "MA Team",

    "HEOR": "HEOR Team",
    "HEOR_TEAM": "HEOR Team",

    "COMPLIANCE": "Compliance Team",
    "COMPLIANCE_TEAM": "Compliance Team",

    "LEGAL": "Legal Team",
    "LEGAL_TEAM": "Legal Team",
    "LEGAL_REVIEW": "Legal Team",

    "ADMIN": "Admin",
    "ADMIN_TEAM": "Admin",

    # Compatibility aliases used by older pipeline/UI code.
    "QA": "MA Team",
    "QA_TEAM": "MA Team",
    "QUALITY": "MA Team",
    "QUALITY_ASSURANCE": "MA Team",

    "AUTH": "MA Team",
    "AUTH_TEAM": "MA Team",
    "AUTHORIZATION": "MA Team",
    "AUTHORIZATION_TEAM": "MA Team",

    "BILLING": "MA Team",
    "BILLING_TEAM": "MA Team",
    "CODING": "MA Team",
    "CODING_TEAM": "MA Team",
}


def _payload_value(payload: Any, key: str, default: Any = None) -> Any:
    if payload is None:
        return default

    if isinstance(payload, dict):
        return payload.get(key, default)

    return getattr(payload, key, default)


def normalize_routing_role(role: Any) -> str:
    raw = str(role or "").strip()

    if not raw:
        return ""

    if raw in ROUTING_ROLES:
        return raw

    token = raw.upper().replace("-", "_").replace(" ", "_")

    return ROLE_ALIASES.get(token, raw)


class CaseService:
    def __init__(self, db: Session):
        self.db = db

    def create_case(self, payload: CaseCreate) -> Case:
        assigned_role = normalize_routing_role(
            payload.assigned_team or payload.assigned_role or "MA Team"
        )
        self._validate_role(assigned_role)

        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        sla_due_at = self._sla_due(assigned_role, payload.priority)

        case = Case(
            case_id=case_id,
            claim_id=payload.claim_id,
            title=payload.title,
            description=payload.description,
            case_type=payload.case_type,
            priority=str(payload.priority or "MEDIUM").upper(),
            assigned_role=assigned_role,
            assigned_team=assigned_role,
            assigned_to=payload.assigned_to or assigned_role,
            sla_due_at=sla_due_at,
            sla_deadline=sla_due_at,
            next_stage=payload.next_stage,
            denial_reason=payload.denial_reason,
            ai_suggestion=payload.ai_suggestion,
            risk_score=payload.risk_score,
            confidence=payload.confidence,
            template_name=payload.template_name,
            confidence_score=payload.confidence_score,
            extraction_quality=payload.extraction_quality,
            metadata_json=payload.metadata,
            created_by=payload.created_by,
        )

        self.db.add(case)
        self.db.flush()

        self._add_assignment(
            case,
            AssignmentUpdate(
                assigned_role=assigned_role,
                assigned_to=payload.assigned_to or assigned_role,
                assigned_by=payload.created_by or "SYSTEM",
                reason="Initial routing",
            ),
        )

        self._audit(
            case.case_id,
            payload.created_by or "SYSTEM",
            "case_created",
            None,
            case.status,
            {"priority": case.priority},
        )

        self.db.commit()
        self.db.refresh(case)
        return case

    def list_cases(
        self,
        status: Optional[str] = None,
        assigned_role: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[Case]:
        query = self.db.query(Case).order_by(Case.created_at.desc())

        if status:
            query = query.filter(Case.status == status.upper())

        if assigned_role:
            query = query.filter(Case.assigned_role == normalize_routing_role(assigned_role))

        if search:
            token = f"%{search}%"
            query = query.filter(
                (Case.case_id.ilike(token))
                | (Case.claim_id.ilike(token))
                | (Case.title.ilike(token))
            )

        return query.limit(min(limit, 500)).all()

    def get_case(self, case_id: str) -> Optional[Case]:
        return self.db.query(Case).filter(Case.case_id == case_id).first()

    def get_case_by_claim(self, claim_id: str) -> Optional[Case]:
        return (
            self.db.query(Case)
            .filter(Case.claim_id == claim_id)
            .order_by(Case.updated_at.desc(), Case.created_at.desc())
            .first()
        )

    def update_status(
        self,
        case: Case,
        status: str,
        actor: str,
        reason: Optional[str] = None,
    ) -> Case:
        status = str(status or "").upper()

        if status not in CASE_STATES:
            raise ValueError(f"Unsupported case status: {status}")

        old_status = case.status
        case.status = status
        case.closed_at = datetime.utcnow() if status == "CLOSED" else case.closed_at
        case.updated_at = datetime.utcnow()

        self._audit(
            case.case_id,
            actor or "SYSTEM",
            "status_changed",
            old_status,
            status,
            {"reason": reason},
        )

        self.db.commit()
        self.db.refresh(case)
        return case

    def assign_case(self, case: Case, payload: AssignmentUpdate) -> Case:
        assigned_role = normalize_routing_role(
            _payload_value(payload, "assigned_role")
            or _payload_value(payload, "assigned_team")
            or _payload_value(payload, "assigned_to")
        )

        self._validate_role(assigned_role)

        assigned_to = _payload_value(payload, "assigned_to") or assigned_role
        assigned_by = _payload_value(payload, "assigned_by") or "SYSTEM"
        reason = _payload_value(payload, "reason") or "Case assignment updated"

        old_role = case.assigned_role

        case.assigned_role = assigned_role
        case.assigned_team = assigned_role
        case.assigned_to = assigned_to
        case.sla_due_at = self._sla_due(assigned_role, case.priority)
        case.sla_deadline = case.sla_due_at
        case.updated_at = datetime.utcnow()

        self.db.query(CaseAssignment).filter(
            CaseAssignment.case_id == case.case_id
        ).update({"active": False})

        self._add_assignment(
            case,
            AssignmentUpdate(
                assigned_role=assigned_role,
                assigned_to=assigned_to,
                assigned_by=assigned_by,
                reason=reason,
            ),
        )

        self._audit(
            case.case_id,
            assigned_by,
            "case_assigned",
            case.status,
            case.status,
            {
                "from_role": old_role,
                "to_role": assigned_role,
                "assigned_to": assigned_to,
                "reason": reason,
            },
        )

        self.db.commit()
        self.db.refresh(case)
        return case

    def add_comment(self, case: Case, author: str, role: str, comment: str) -> CaseComment:
        normalized_role = normalize_routing_role(role) or role

        comment_row = CaseComment(
            case_id=case.case_id,
            author=author,
            role=normalized_role,
            comment=comment,
        )

        self.db.add(comment_row)
        case.updated_at = datetime.utcnow()

        self._audit(
            case.case_id,
            author or "SYSTEM",
            "comment_added",
            case.status,
            case.status,
            {"role": normalized_role},
        )

        self.db.commit()
        self.db.refresh(comment_row)
        return comment_row

    def auto_escalate_overdue(self) -> list[Case]:
        now = datetime.utcnow()

        overdue = (
            self.db.query(Case)
            .filter(Case.status.notin_(["CLOSED", "APPROVED", "REJECTED"]))
            .filter(Case.sla_due_at < now)
            .all()
        )

        escalated = []

        for case in overdue:
            escalated.append(
                self.escalate_case(
                    case,
                    "SLA overdue",
                    actor="SLA_TIMER",
                    commit=False,
                )
            )

        self.db.commit()
        return escalated

    def escalate_case(
        self,
        case: Case,
        reason: str,
        actor: str = "SYSTEM",
        commit: bool = True,
    ) -> Case:
        old_role = normalize_routing_role(case.assigned_role) or "MA Team"
        next_role = ESCALATION_ROUTE.get(old_role, "Admin")

        case.escalation_level = (case.escalation_level or 0) + 1
        case.assigned_role = next_role
        case.assigned_team = next_role
        case.status = "ESCALATED"
        case.sla_due_at = self._sla_due(next_role, "HIGH")
        case.sla_deadline = case.sla_due_at
        case.next_stage = "ESCALATED_REVIEW"
        case.updated_at = datetime.utcnow()

        escalation = CaseEscalation(
            case_id=case.case_id,
            level=case.escalation_level,
            from_role=old_role,
            to_role=next_role,
            reason=reason,
        )

        self.db.add(escalation)

        self._audit(
            case.case_id,
            actor or "SYSTEM",
            "case_escalated",
            "OVERDUE",
            "ESCALATED",
            {
                "from_role": old_role,
                "to_role": next_role,
                "reason": reason,
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(case)

        return case

    def dashboard(self) -> Dict[str, Any]:
        self.auto_escalate_overdue()

        cases = self.db.query(Case).all()
        by_status: Dict[str, int] = {}
        by_role: Dict[str, int] = {}
        overdue = 0
        due_soon = 0
        now = datetime.utcnow()

        for case in cases:
            by_status[case.status] = by_status.get(case.status, 0) + 1
            by_role[case.assigned_role] = by_role.get(case.assigned_role, 0) + 1

            if case.sla_due_at and case.sla_due_at < now:
                overdue += 1
            elif case.sla_due_at and case.sla_due_at < now + timedelta(hours=1):
                due_soon += 1

        return {
            "total": len(cases),
            "open": sum(
                by_status.get(s, 0)
                for s in [
                    "NEW",
                    "IN_REVIEW",
                    "COMPLIANCE_REVIEW",
                    "LEGAL_REVIEW",
                    "ESCALATED",
                ]
            ),
            "overdue": overdue,
            "due_soon": due_soon,
            "escalated": by_status.get("ESCALATED", 0),
            "approved": by_status.get("APPROVED", 0),
            "closed": by_status.get("CLOSED", 0),
            "by_status": by_status,
            "by_role": by_role,
            "sla_attainment": round(
                ((len(cases) - overdue) / len(cases)) * 100,
                2,
            )
            if cases
            else 100,
        }

    def escalations(self) -> list[CaseEscalation]:
        return (
            self.db.query(CaseEscalation)
            .order_by(CaseEscalation.created_at.desc())
            .limit(200)
            .all()
        )

    def serialize_case(self, case: Case, include_children: bool = True) -> Dict[str, Any]:
        self._refresh_sla_status(case)

        data = {
            "case_id": case.case_id,
            "claim_id": case.claim_id,
            "title": case.title,
            "description": case.description,
            "case_type": case.case_type,
            "status": case.status,
            "priority": case.priority,
            "assigned_role": case.assigned_role,
            "assigned_team": case.assigned_team or case.assigned_role,
            "current_owner": case.assigned_to or case.assigned_team or case.assigned_role,
            "assigned_to": case.assigned_to,
            "escalation_level": case.escalation_level or 0,
            "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None,
            "sla_deadline": (case.sla_deadline or case.sla_due_at).isoformat()
            if (case.sla_deadline or case.sla_due_at)
            else None,
            "sla_status": case.sla_status,
            "next_stage": case.next_stage,
            "denial_reason": case.denial_reason,
            "ai_suggestion": case.ai_suggestion,
            "risk_score": case.risk_score or 0,
            "confidence": case.confidence or 0,
            "corrected_fields": case.corrected_fields or [],
            "template_name": case.template_name,
            "confidence_score": case.confidence_score or 0,
            "extraction_quality": case.extraction_quality,
            "metadata": case.metadata_json or {},
            "created_by": case.created_by,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
        }

        if include_children:
            data["comments"] = [self._serialize_comment(item) for item in case.comments]
            data["assignments"] = [
                self._serialize_assignment(item) for item in case.assignments
            ]
            data["audit_logs"] = [self._serialize_audit(item) for item in case.audit_logs]
            data["escalations"] = [
                self._serialize_escalation(item) for item in case.escalations
            ]

        return data

    def _sla_due(self, role: str, priority: str = "MEDIUM") -> datetime:
        normalized_role = normalize_routing_role(role) or "MA Team"

        hours = ROLE_SLA_HOURS.get(normalized_role, 4)

        if str(priority or "").upper() == "HIGH":
            hours = max(1, hours // 2)

        return datetime.utcnow() + timedelta(hours=hours)

    def _validate_role(self, role: str) -> None:
        normalized_role = normalize_routing_role(role)

        if normalized_role not in ROUTING_ROLES:
            raise ValueError(f"Unsupported routing role: {role}")

    def _add_assignment(self, case: Case, payload: AssignmentUpdate) -> None:
        assigned_role = normalize_routing_role(payload.assigned_role)
        self._validate_role(assigned_role)

        self.db.add(
            CaseAssignment(
                case_id=case.case_id,
                assigned_role=assigned_role,
                assigned_to=payload.assigned_to or assigned_role,
                assigned_by=payload.assigned_by or "SYSTEM",
                reason=payload.reason,
            )
        )

    def _audit(
        self,
        case_id: str,
        actor: str,
        action: str,
        from_status: Optional[str],
        to_status: Optional[str],
        details: Dict[str, Any],
    ) -> None:
        self.db.add(
            CaseAuditLog(
                case_id=case_id,
                actor=actor or "SYSTEM",
                action=action,
                from_status=from_status,
                to_status=to_status,
                details=details or {},
            )
        )

    def _refresh_sla_status(self, case: Case) -> None:
        if not case.sla_due_at or case.status in ["CLOSED", "APPROVED", "REJECTED"]:
            case.sla_status = "COMPLETE"
            return

        now = datetime.utcnow()

        if case.sla_due_at < now:
            case.sla_status = "OVERDUE"
        elif case.sla_due_at < now + timedelta(hours=1):
            case.sla_status = "DUE_SOON"
        else:
            case.sla_status = "ON_TRACK"

    @staticmethod
    def _serialize_comment(item: CaseComment) -> Dict[str, Any]:
        return {
            "id": item.id,
            "author": item.author,
            "role": item.role,
            "comment": item.comment,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_assignment(item: CaseAssignment) -> Dict[str, Any]:
        return {
            "id": item.id,
            "assigned_role": item.assigned_role,
            "assigned_to": item.assigned_to,
            "assigned_by": item.assigned_by,
            "reason": item.reason,
            "active": item.active,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_audit(item: CaseAuditLog) -> Dict[str, Any]:
        return {
            "id": item.id,
            "actor": item.actor,
            "action": item.action,
            "from_status": item.from_status,
            "to_status": item.to_status,
            "details": item.details or {},
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_escalation(item: CaseEscalation) -> Dict[str, Any]:
        return {
            "id": item.id,
            "level": item.level,
            "from_role": item.from_role,
            "to_role": item.to_role,
            "reason": item.reason,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }
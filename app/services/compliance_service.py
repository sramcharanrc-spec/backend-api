from sqlalchemy.orm import Session
from app.models.compliance_audit_model import ComplianceAudit


class ComplianceService:
    def __init__(self, db):
        self.db = db

    def create_audit(self, audit_data: dict) -> ComplianceAudit:
        """
        Create compliance audit safely.

        This prevents runtime errors when the agent sends fields
        that are not direct columns on ComplianceAudit, such as:
        - duration_seconds
        - risk_score
        - checked_fields
        - extra metadata
        """

        audit_data = audit_data or {}

        allowed_fields = {
            column.name
            for column in ComplianceAudit.__table__.columns
        }

        clean_data = {
            key: value
            for key, value in audit_data.items()
            if key in allowed_fields
        }

        extra_data = {
            key: value
            for key, value in audit_data.items()
            if key not in allowed_fields
        }

        if extra_data:
            audit_details = clean_data.get("audit_details") or {}

            if not isinstance(audit_details, dict):
                audit_details = {
                    "value": audit_details
                }

            audit_details["extra"] = extra_data
            clean_data["audit_details"] = audit_details

        audit = ComplianceAudit(**clean_data)

        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)

        return audit

    def get_audits_by_claim(self, claim_id: str):
        return (
            self.db.query(ComplianceAudit)
            .filter(ComplianceAudit.claim_id == claim_id)
            .all()
        )

    def get_all_audits(self):
        return self.db.query(ComplianceAudit).all()
from app.agents.base.base_agent import BaseAgent
from datetime import datetime


class ComplianceAgent(BaseAgent):

    async def run(self, claim):

        audit_record = {
            "claim_id": claim.get("claim_id"),
            "timestamp": datetime.utcnow().isoformat(),
            "status": str(claim.get("status")),   # safe conversion
            "submission_id": claim.get("submission_id")
        }

        print("[ComplianceGuardian] Audit log:", audit_record)

        return {
            "claim": claim,
            "compliance_logged": True,
            "audit": audit_record   # ✅ IMPORTANT for UI
        }
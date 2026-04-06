from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit

class EligibilityAgent(BaseAgent):

    async def run(self, claim):

        print("🧾 [EligibilityAgent] Started")

        if not claim.get("patient"):
            raise ValueError("Missing patient info")

        await manager.send_event("eligibility", "running")

        claim["eligibility_status"] = "verified"

        log_audit(claim.get("claim_id"), "eligibility", "completed", {
            "eligibility_status": "verified"
        })

        await manager.send_event("eligibility", "completed", {
            "eligibility_status": "verified"
        })

        return {
            "claim": claim,
            "pipeline": {
                "steps": {
                    "eligibility_checked": True
                }
            },
            "stage": "eligibility_done"
        }
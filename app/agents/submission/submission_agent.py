# from app.agents.base.base_agent import BaseAgent
# from app.services.audit_service import log_audit
# from app.websocket.manager import manager
# import uuid


# class SubmissionAgent(BaseAgent):

#     async def run(self, claim):

#         print("📤 [SubmissionAgent] Started")
#         await self.log("[SubmissionAgent] Submitting claim")

#         await manager.send_event("submission", "running")

#         try:
#             # -------------------------
#             # Generate submission ID
#             # -------------------------
#             submission_id = f"SUB-{uuid.uuid4().hex[:8]}"
#             claim["submission_id"] = submission_id

#             claim["status"] = "submitted"

#             # -------------------------
#             # Audit
#             # -------------------------
#             log_audit(
#                 claim.get("claim_id"),
#                 "submission",
#                 "completed",
#                 {"submission_id": submission_id}
#             )

#             await manager.send_event("submission", "completed", {
#                 "submission_id": submission_id
#             })

#             print("✅ Submission completed")

#             return {
#                 "claim": claim,

#                 "pipeline": {
#                     "steps": {
#                         "submitted": True
#                     }
#                 },

#                 "stage": "submitted"
#             }

#         except Exception as e:
#             print("❌ SubmissionAgent Error:", str(e))

#             log_audit(
#                 claim.get("claim_id"),
#                 "submission",
#                 "failed",
#                 {"error": str(e)}
#             )

#             await manager.send_event("submission", "failed", {"error": str(e)})

#             raise

import uuid
from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager

class SubmissionAgent(BaseAgent):

    async def run(self, claim):

        print("📤 [SubmissionAgent] Started")

        if not claim.get("services"):
            raise ValueError("No services to submit")

        await manager.send_event("submission", "running")

        claim["submission_id"] = f"SUB-{uuid.uuid4().hex[:8]}"
        claim["status"] = "submitted"

        await manager.send_event("submission", "completed", {
            "submission_id": claim["submission_id"]
        })

        return {
            "claim": claim,
            "pipeline": {
                "steps": {
                    "submitted": True
                }
            },
            "stage": "submitted"
        }
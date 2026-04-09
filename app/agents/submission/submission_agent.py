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

# import uuid
# from app.agents.base.base_agent import BaseAgent
# from app.websocket.manager import manager

# class SubmissionAgent(BaseAgent):

#     async def run(self, claim):

#         print("📤 [SubmissionAgent] Started")

#         if not claim.get("services"):
#             raise ValueError("No services to submit")

#         await manager.send_event("submission", "running")

#         claim["submission_id"] = f"SUB-{uuid.uuid4().hex[:8]}"
#         claim["status"] = "submitted"

#         await manager.send_event("submission", "completed", {
#             "submission_id": claim["submission_id"]
#         })

#         return {
#             "claim": claim,
#             "pipeline": {
#                 "steps": {
#                     "submitted": True
#                 }
#             },
#             "stage": "submitted"
#         }

# import uuid
# from app.agents.base.base_agent import BaseAgent
# from app.websocket.manager import manager

# # 🆕 ADD THESE
# from app.rcm.clearinghouse_client import send_to_clearinghouse
# from app.intake.db_service import update_record_status, get_record_by_id, save_record


# class SubmissionAgent(BaseAgent):

#     async def run(self, claim):

#         print("📤 [SubmissionAgent] Started")

#         if not claim.get("services"):
#             raise ValueError("No services to submit")

#         await manager.send_event("submission", "running")

#         # -------------------------
#         # 1. Generate submission ID
#         # -------------------------
#         submission_id = f"SUB-{uuid.uuid4().hex[:8]}"
#         claim["submission_id"] = submission_id

#         # -------------------------
#         # 🆕 2. Generate EDI
#         # -------------------------
#         edi_payload = f"EDI837::{submission_id}"

#         print("📦 EDI Generated:", edi_payload)

#         # -------------------------
#         # 🆕 3. Send to Clearinghouse
#         # -------------------------
#         ch_response = send_to_clearinghouse(edi_payload)

#         print("📡 Clearinghouse Response:", ch_response)

#         # -------------------------
#         # 🆕 4. Save submission (DB)
#         # -------------------------
#         update_record_status(
#             {
#                 "submission_id": submission_id,
#                 "claim_id": claim.get("claim_id")
#             },
#             {
#                 "transmission_id": ch_response.get("transmission_id"),
#                 "edi": edi_payload
#             }
#         )

#         # -------------------------
#         # 5. Update claim
#         # -------------------------
#         claim["status"] = "submitted"

#         claim["submission"] = {
#             "submission_id": submission_id,
#             "edi": edi_payload,
#             "response": ch_response
#         }

#         # -------------------------
#         # WebSocket update
#         # -------------------------
#         await manager.send_event("submission", "completed", {
#             "submission_id": submission_id
#         })

#         return {
#             "claim": claim,
#             "pipeline": {
#                 "steps": {
#                     "submitted": True
#                 }
#             },
#             "stage": "submitted"
#         }

import datetime
import uuid
from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from datetime import datetime
# External services
from app.rcm.clearinghouse_client import send_to_clearinghouse
from app.intake.db_service import (
    update_record_status,
    get_record_by_id,
    save_record
)


class SubmissionAgent(BaseAgent):

    async def run(self, claim):

        print("📤 [SubmissionAgent] Started")

        # -------------------------
        # 0. Basic validation
        # -------------------------
        if not claim.get("services"):
            raise ValueError("No services to submit")

        await manager.send_event("submission", "running")

        try:
            # -------------------------
            # 1. Generate submission ID
            # -------------------------
            submission_id = f"SUB-{uuid.uuid4().hex[:8]}"
            claim["submission_id"] = submission_id

            # -------------------------
            # 2. Generate EDI payload
            # -------------------------
            edi_payload = f"EDI837::{submission_id}"
            print("📦 EDI Generated:", edi_payload)

            # -------------------------
            # 3. Send to Clearinghouse
            # -------------------------
            ch_response = send_to_clearinghouse(edi_payload)
            print("📡 Clearinghouse Response:", ch_response)

            # -------------------------
            # 4. Update DB (submission info)
            # -------------------------
            update_record_status(
                {
                    "submission_id": submission_id,
                    "claim_id": claim.get("claim_id")
                },
                {
                    "transmission_id": ch_response.get("transmission_id"),
                    "edi": edi_payload
                }
            )

            # -------------------------
            # 5. Update claim object
            # -------------------------
            claim["status"] = "PENDING_APPROVAL"  # 🔥 IMPORTANT
            claim["submission"] = {
                "submission_id": submission_id,
                "edi": edi_payload,
                "response": ch_response
            }

            # -------------------------
            # 6. Update full record in DB
            # -------------------------
            record = get_record_by_id(claim.get("claim_id"))

            if record:
                # Ensure pipeline structure
                if "pipeline" not in record:
                    record["pipeline"] = {"steps": {}}

                if "steps" not in record["pipeline"]:
                    record["pipeline"]["steps"] = {}

                # Update pipeline state
                record["pipeline"]["steps"]["submitted"] = True

                # 🔥 STOP POINT STATUS
                record["status"] = "PENDING_APPROVAL"

                # Store clearinghouse response
                record["clearinghouse"] = ch_response

                record["submitted_at"] = datetime.utcnow().isoformat()

                # Optional flag for UI
                record["approval_required"] = True

                save_record(record)

            # -------------------------
            # 7. Notify UI (WebSocket)
            # -------------------------
            await manager.send_event(
                "submission",
                "completed",
                {
                    "submission_id": submission_id,
                    "status": "PENDING_APPROVAL"
                }
            )

            print("⏸ Pipeline paused. Waiting for user approval...")

            # -------------------------
            # 🚨 8. STOP PIPELINE HERE
            # -------------------------
            return {
                "claim": claim,
                "pipeline": {
                    "steps": {
                        "submitted": True
                    }
                },
                "stage": "PENDING_APPROVAL"  # 🔥 KEY CHANGE
            }

        except Exception as e:
            print("❌ SubmissionAgent Error:", str(e))

            await manager.send_event(
                "submission",
                "failed",
                {"error": str(e)}
            )

            raise
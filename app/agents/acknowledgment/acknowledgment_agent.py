from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.agents.submission.clearinghouse_client import ClearinghouseClient
from app.services.audit_service import log_audit

# ✅ REQUIRED IMPORTS
from app.rcm.edi_responses import generate_999_ack, generate_277ca
from app.intake.db_service import update_record_status
from app.rcm.submission import record_ack


class AcknowledgmentAgent(BaseAgent):

    async def run(self, claim):
        print("📨 [AcknowledgmentAgent] Started")

        if not claim.get("submission_id"):
            raise ValueError("No submission_id found to track")

        await manager.send_event("acknowledgment", "running")

        submission_id = claim["submission_id"]

        # -------------------------
        # 🔹 1. 999 ACK (syntax level)
        # -------------------------
        ack_999 = generate_999_ack()
        print("✅ 999 ACK:", ack_999)

        # -------------------------
        # 🔹 2. Get clearinghouse status
        # -------------------------
        client = ClearinghouseClient()
        response = client.check_status(submission_id)

        # -------------------------
        # 🔹 3. Generate 277CA (business level)
        # -------------------------
        ack_277 = generate_277ca(
            submission_id,
            response.get("status") != "DENIED"
        )

        print("📩 277CA:", ack_277)

        # -------------------------
        # 🔹 4. Record ACK (DB / tracking)
        # -------------------------
        record_ack(
            submission_id=submission_id,
            status=ack_277["status"],
            reason=ack_277.get("error"),
            claim_id=claim.get("claim_id")
        )

        # -------------------------
        # 🔹 5. Update DynamoDB status
        # -------------------------
        if ack_277["status"] == "REJECTED":
            update_record_status(claim["claim_id"], "DENIED")
        else:
            update_record_status(claim["claim_id"], "ACKNOWLEDGED")

        # -------------------------
        # 🔹 6. Attach ACK data to claim
        # -------------------------
        claim["ack"] = {
            "ack_999": ack_999,
            "ack_277": ack_277
        }

        # -------------------------
        # 🔹 7. Map final status
        # -------------------------
        status = response.get("status")

        if status == "DENIED":
            claim["status"] = "denied"
            claim["denial_code"] = response.get("denial_code")

        elif status == "PAID":
            claim["status"] = "paid"

        else:
            claim["status"] = "acknowledged"

        # -------------------------
        # 🔹 8. Audit log
        # -------------------------
        log_audit(
            claim.get("claim_id"),
            "acknowledgment",
            "completed",
            {
                "999": ack_999,
                "277ca": ack_277,
                "raw": response
            }
        )

        # -------------------------
        # 🔹 9. WebSocket update
        # -------------------------
        await manager.send_event("acknowledgment", "completed", {
            "status": claim["status"],
            "ack_277": ack_277
        })

        return {
            "claim": claim,
            "pipeline": {
                "steps": {
                    "acknowledged": True
                }
            },
            "stage": "acknowledged"
        }
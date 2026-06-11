import time
from datetime import datetime

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.agents.submission.clearinghouse_client import ClearinghouseClient
from app.services.audit_service import log_audit
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event

from app.rcm.edi_responses import generate_999_ack, generate_277ca
from app.intake.db_service import update_record_status
from app.rcm.submission import record_ack


class AcknowledgmentAgent(BaseAgent):
    """
    Acknowledgment Agent.

    Responsibilities:
    - Generate 999 acknowledgment
    - Check clearinghouse status
    - Generate 277CA
    - Record acknowledgment result
    - Update claim/database status
    - Send detailed API/WebSocket-ready agent output
    """

    AGENT_KEY = "acknowledgment"
    AGENT_NAME = "AcknowledgmentAgent"
    STAGE = "ACKNOWLEDGMENT"
    PROGRESS = 74

    async def run(self, claim):
        start_time = time.time()
        started_at = datetime.utcnow().isoformat()

        claim = claim or {}
        claim_id = claim.get("claim_id")
        submission_id = claim.get("submission_id")

        print("\n" + "=" * 80)
        print("📨 [AcknowledgmentAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📤 Submission ID: {submission_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        if not claim_id:
            raise ValueError("No claim_id found for acknowledgment tracking")

        if not submission_id:
            raise ValueError("No submission_id found to track")

        await send_pipeline_event(
            manager,
            topic=self.AGENT_KEY,
            action="running",
            claim_id=claim_id,
            stage=self.STAGE,
            status="RUNNING",
            progress=self.PROGRESS,
            current_stage=self.STAGE,
            current_agent=self.AGENT_NAME,
            active_step=self.AGENT_KEY,
            pipeline_state="ACKNOWLEDGMENT_RUNNING",
            pipeline_status="RUNNING",
            message="Acknowledgment Agent started",
            extra={"submission_id": submission_id},
        )

        try:
            # -------------------------
            # 1. Generate 999 ACK
            # -------------------------
            print("➡️ [1] Generating 999 ACK...")
            ack_999 = generate_999_ack()

            print("✅ 999 ACK:")
            print(ack_999)

            # -------------------------
            # 2. Check clearinghouse status
            # -------------------------
            print("➡️ [2] Checking clearinghouse status...")
            client = ClearinghouseClient()
            response = client.check_status(submission_id) or {}

            print("📬 Clearinghouse response:")
            print(response)

            clearinghouse_status = response.get("status")

            # -------------------------
            # 3. Generate 277CA
            # -------------------------
            print("➡️ [3] Generating 277CA...")
            ack_277 = generate_277ca(
                submission_id,
                clearinghouse_status != "DENIED",
            )

            print("📩 277CA:")
            print(ack_277)

            # -------------------------
            # 4. Record ACK
            # -------------------------
            print("➡️ [4] Recording acknowledgment...")

            record_ack(
                submission_id=submission_id,
                status=ack_277.get("status"),
                reason=ack_277.get("error"),
                claim_id=claim_id,
            )

            print("✅ ACK recorded")

            # -------------------------
            # 5. Map final status
            # -------------------------
            print("➡️ [5] Mapping final claim status...")

            if clearinghouse_status == "DENIED":
                claim_status = "denied"
                db_status = "DENIED"
                result_status = "COMPLETED"
                next_agent = "DenialAgent"
                claim["denial_code"] = response.get("denial_code")

            elif clearinghouse_status == "PAID":
                claim_status = "paid"
                db_status = "PAID"
                result_status = "COMPLETED"
                next_agent = "PaymentAgent"

            elif ack_277.get("status") == "REJECTED":
                claim_status = "rejected"
                db_status = "REJECTED"
                result_status = "FAILED"
                next_agent = "CaseOrchestrator"

            else:
                claim_status = "acknowledged"
                db_status = "ACKNOWLEDGED"
                result_status = "COMPLETED"
                next_agent = "DenialAgent"

            update_record_status(claim_id, db_status)

            print(f"✅ Claim status: {claim_status}")
            print(f"✅ DB status: {db_status}")
            print(f"⏭️ Next agent: {next_agent}")

            # -------------------------
            # 6. Build ACK payload
            # -------------------------
            completed_at = datetime.utcnow().isoformat()
            duration_seconds = round(time.time() - start_time, 2)

            ack_payload = {
                "claim_id": claim_id,
                "agent": self.AGENT_NAME,
                "submission_id": submission_id,
                "status": claim_status,
                "result_status": result_status,
                "db_status": db_status,
                "clearinghouse_status": clearinghouse_status,
                "denial_code": response.get("denial_code"),
                "ack_999": ack_999,
                "ack_277": ack_277,
                "raw_response": response,
                "duration_seconds": duration_seconds,
                "next_agent": next_agent,
            }

            agent_detail = {
                "key": self.AGENT_KEY,
                "agent": self.AGENT_NAME,
                "stage": self.STAGE,
                "status": result_status,
                "active_step": "Acknowledgment received and claim status mapped",
                "message": f"Clearinghouse status: {clearinghouse_status or claim_status}",
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds,
                "progress": self.PROGRESS,
                "passed": result_status == "COMPLETED",
                "score": None,
                "risk_score": None,
                "risk_score_percent": None,
                "errors": [] if result_status == "COMPLETED" else [ack_277.get("error") or "Acknowledgment rejected"],
                "warnings": [],
                "output": ack_payload,
                "next_agent": next_agent,
            }

            # -------------------------
            # 7. Save result onto claim
            # -------------------------
            claim["ack"] = ack_payload
            claim["acknowledgment"] = ack_payload
            claim["status"] = claim_status
            claim["acknowledged_at"] = completed_at
            claim["ack_duration_seconds"] = duration_seconds

            claim["agents"] = claim.get("agents") or {}
            claim["agents"][self.AGENT_KEY] = agent_detail

            claim["pipeline"] = claim.get("pipeline") or {}
            claim["pipeline"]["steps"] = claim["pipeline"].get("steps") or {}
            claim["pipeline"]["steps"]["acknowledged"] = True

            claim["current_stage"] = self.STAGE
            claim["current_agent"] = self.AGENT_NAME
            claim["active_step"] = self.AGENT_KEY
            claim["progress"] = self.PROGRESS
            claim["pipeline_state"] = "ACKNOWLEDGMENT_COMPLETED"
            claim["pipeline_status"] = result_status
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage=self.STAGE,
                status=result_status,
                progress=self.PROGRESS,
                current_stage=self.STAGE,
                current_agent=self.AGENT_NAME,
                active_step=self.AGENT_KEY,
                pipeline_state="ACKNOWLEDGMENT_COMPLETED",
                pipeline_status=result_status,
                message=f"Clearinghouse status: {clearinghouse_status or claim_status}",
            )
            claim["pipeline"]["steps"]["acknowledged"] = True

            # -------------------------
            # 8. Audit log
            # -------------------------
            print("➡️ [6] Writing audit log...")

            log_audit(
                claim_id,
                self.AGENT_KEY,
                result_status.lower(),
                {
                    "999": ack_999,
                    "277ca": ack_277,
                    "raw": response,
                    "status": claim_status,
                    "db_status": db_status,
                    "duration_seconds": duration_seconds,
                    "agent_detail": agent_detail,
                },
            )

            print("✅ Audit log written")

            # -------------------------
            # 9. WebSocket update
            # -------------------------
            print("➡️ [7] Sending acknowledgment event to frontend...")

            await manager.send_event(
                self.AGENT_KEY,
                result_status.lower(),
                {
                    **ack_payload,
                    "stage": self.STAGE,
                    "current_stage": self.STAGE,
                    "current_agent": self.AGENT_NAME,
                    "active_step": self.AGENT_KEY,
                    "progress": self.PROGRESS,
                    "pipeline_state": "ACKNOWLEDGMENT_COMPLETED",
                    "pipeline_status": result_status,
                    "agent_detail": agent_detail,
                },
            )

            print("✅ Acknowledgment event sent")
            print(f"⏱️ Acknowledgment duration: {duration_seconds}s")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "stage": self.STAGE,
                "status": result_status,
                "claim_status": claim_status,
                "acknowledgment": ack_payload,
                "agent_detail": agent_detail,
                "duration_seconds": duration_seconds,
            }

        except Exception as error:
            completed_at = datetime.utcnow().isoformat()
            duration_seconds = round(time.time() - start_time, 2)

            error_message = str(error)

            print("❌ [AcknowledgmentAgent] FAILED")
            print(f"❌ Error: {error_message}")
            print(f"⏱️ Acknowledgment duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            agent_detail = {
                "key": self.AGENT_KEY,
                "agent": self.AGENT_NAME,
                "stage": self.STAGE,
                "status": "FAILED",
                "active_step": "Acknowledgment processing failed",
                "message": error_message,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds,
                "progress": self.PROGRESS,
                "passed": False,
                "score": None,
                "risk_score": None,
                "risk_score_percent": None,
                "errors": [error_message],
                "warnings": [],
                "output": {
                    "claim_id": claim_id,
                    "submission_id": submission_id,
                    "error": error_message,
                },
                "next_agent": "CaseOrchestrator",
            }

            claim["agents"] = claim.get("agents") or {}
            claim["agents"][self.AGENT_KEY] = agent_detail

            claim["pipeline"] = claim.get("pipeline") or {}
            claim["pipeline"]["steps"] = claim["pipeline"].get("steps") or {}
            claim["pipeline"]["steps"]["acknowledged"] = False

            claim["current_stage"] = self.STAGE
            claim["current_agent"] = self.AGENT_NAME
            claim["active_step"] = self.AGENT_KEY
            claim["progress"] = self.PROGRESS
            claim["pipeline_state"] = "ACKNOWLEDGMENT_FAILED"
            claim["pipeline_status"] = "FAILED"
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage=self.STAGE,
                status="FAILED",
                progress=self.PROGRESS,
                current_stage=self.STAGE,
                current_agent=self.AGENT_NAME,
                active_step=self.AGENT_KEY,
                pipeline_state="ACKNOWLEDGMENT_FAILED",
                pipeline_status="FAILED",
                message=error_message,
            )
            claim["pipeline"]["steps"]["acknowledged"] = False

            await manager.send_event(
                self.AGENT_KEY,
                "failed",
                {
                    "claim_id": claim_id,
                    "submission_id": submission_id,
                    "stage": self.STAGE,
                    "current_stage": self.STAGE,
                    "current_agent": self.AGENT_NAME,
                    "active_step": self.AGENT_KEY,
                    "progress": self.PROGRESS,
                    "pipeline_state": "ACKNOWLEDGMENT_FAILED",
                    "pipeline_status": "FAILED",
                    "error": error_message,
                    "duration_seconds": duration_seconds,
                    "next_agent": "CaseOrchestrator",
                    "agent_detail": agent_detail,
                },
            )

            log_audit(
                claim_id,
                self.AGENT_KEY,
                "failed",
                {
                    "error": error_message,
                    "duration_seconds": duration_seconds,
                    "agent_detail": agent_detail,
                },
            )

            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "stage": self.STAGE,
                "status": "FAILED",
                "error": error_message,
                "agent_detail": agent_detail,
                "duration_seconds": duration_seconds,
            }

# from app.agents.base.base_agent import BaseAgent
# from datetime import datetime
# import logging
# from app.services.feedback_service import FeedbackService
# from app.db.database import get_db

# logger = logging.getLogger(__name__)

# class FeedbackLoopAgent(BaseAgent):
#     """
#     Feedback Loop Agent

#     Responsibilities:
#     * capture claim outcomes
#     * capture denial reasons
#     * capture validation corrections
#     * capture HITL modifications
#     * capture payment outcomes
#     * send signals to learning agent
#     """

#     async def run(self, claim):
#         logger.info("🔁 [FEEDBACK_LOOP] Feedback processing started")

#         feedback_data = {
#             "claim_id": claim.get("claim_id"),
#             "submission_id": claim.get("submission_id"),
#             "timestamp": datetime.utcnow().isoformat(),
#             "outcome": claim.get("status"),
#             "denial_reason": claim.get("denial", {}).get("reason"),
#             "validation_corrections": claim.get("validation", {}).get("corrections", []),
#             "hitl_modifications": claim.get("case", {}).get("modifications", []),
#             "payment_outcome": claim.get("payment", {}).get("status"),
#             "risk_score": claim.get("analytics", {}).get("risk_score"),
#         }

#         # Store in database
#         db = next(get_db())
#         service = FeedbackService(db)
#         service.create_feedback(feedback_data)
#         logger.info(f"💾 [FEEDBACK_LOOP] Feedback stored for claim {claim.get('claim_id')}")

#         # Signal to learning agent
#         claim["feedback_captured"] = True

#         return {
#             "claim": claim,
#             "feedback_logged": True,
#             "feedback_data": feedback_data
#         }

import logging
import time
from datetime import datetime

from app.agents.base.base_agent import BaseAgent
from app.services.feedback_service import FeedbackService
from app.services.analytics_service import update_metrics
from app.db.database import get_db
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


class FeedbackLoopAgent(BaseAgent):
    """
    Feedback Loop Agent

    Responsibilities:
    - Capture claim outcome
    - Capture denial reasons
    - Capture validation corrections
    - Capture HITL modifications
    - Capture payment outcomes
    - Store feedback for learning
    - Send signals to LearningAgent
    """

    async def run(self, claim):
        start_time = time.time()
        claim = claim or {}

        claim_id = claim.get("claim_id", "UNKNOWN")
        submission_id = claim.get("submission_id")

        print("\n" + "=" * 80)
        print("🔁 [FeedbackLoopAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📤 Submission ID: {submission_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        logger.info("🔁 [FEEDBACK_LOOP] Feedback processing started")

        await manager.send_event("feedback", "running", {
            "claim_id": claim_id,
            "submission_id": submission_id,
            "message": "Feedback Loop Agent started",
        })

        try:
            # ---------------------------------------------------
            # Step 1: Read source objects
            # ---------------------------------------------------
            print("➡️ [1] Reading claim outcome sources...")

            validation = claim.get("validation") or {}
            denial = claim.get("denial") or {}
            case_data = claim.get("case") or {}
            payment = claim.get("payment_result") or claim.get("payment") or {}
            analytics = claim.get("analytics") or {}
            compliance = claim.get("compliance") or {}

            outcome = (
                claim.get("status")
                or payment.get("payment_status")
                or denial.get("status")
                or "unknown"
            )

            denial_reason = (
                denial.get("reason")
                or denial.get("root_cause")
                or claim.get("denial_reason")
            )

            denial_code = (
                denial.get("denial_code")
                or claim.get("denial_code")
            )

            validation_corrections = (
                validation.get("corrections")
                or denial.get("suggested_corrections")
                or []
            )

            hitl_modifications = (
                case_data.get("modifications")
                or case_data.get("changes")
                or []
            )

            payment_outcome = (
                payment.get("payment_status")
                or payment.get("status")
                or claim.get("payment_status")
            )

            risk_score = self._normalize_score(
                analytics.get("risk_score")
                or compliance.get("risk_score")
                or validation.get("risk_score")
                or denial.get("risk_score")
                or claim.get("risk_score")
                or 0
            )

            print(f"📌 Outcome: {outcome}")
            print(f"📌 Denial code: {denial_code}")
            print(f"📌 Denial reason: {denial_reason}")
            print(f"📌 Payment outcome: {payment_outcome}")
            print(f"📊 Risk score: {risk_score}")

            # ---------------------------------------------------
            # Step 2: Build feedback data
            # ---------------------------------------------------
            print("➡️ [2] Building feedback data...")

            feedback_data = {
                "claim_id": claim_id,
                "submission_id": submission_id,
                "timestamp": datetime.utcnow().isoformat(),
                "outcome": outcome,
                "denial_code": denial_code,
                "denial_reason": denial_reason,
                "validation_corrections": validation_corrections,
                "hitl_modifications": hitl_modifications,
                "payment_outcome": payment_outcome,
                "risk_score": risk_score,
                "risk_score_percent": round(risk_score * 100),
                "source_signals": {
                    "validation_status": validation.get("status"),
                    "validation_score": validation.get("validation_score"),
                    "compliance_status": compliance.get("compliance_status"),
                    "denial_found": denial.get("denial_found"),
                    "payment_status": payment_outcome,
                    "case_status": case_data.get("status"),
                },
            }

            print("✅ Feedback data built")
            print(f"📦 Feedback data: {feedback_data}")

            # ---------------------------------------------------
            # Step 3: Store feedback
            # ---------------------------------------------------
            print("➡️ [3] Storing feedback in database...")

            db_gen = get_db()
            db = next(db_gen)

            try:
                service = FeedbackService(db)
                service.create_feedback(feedback_data)
                print(f"✅ Feedback stored for claim {claim_id}")

            finally:
                db.close()

            logger.info(f"💾 [FEEDBACK_LOOP] Feedback stored for claim {claim_id}")

            # ---------------------------------------------------
            # Step 4: Attach feedback to claim
            # ---------------------------------------------------
            print("➡️ [4] Attaching feedback data to claim...")

            duration_seconds = round(time.time() - start_time, 2)

            feedback_payload = {
                "claim_id": claim_id,
                "agent": "FeedbackLoopAgent",
                "status": "completed",
                "feedback_logged": True,
                "feedback_captured": True,
                "feedback_data": feedback_data,
                "duration_seconds": duration_seconds,
                "next_agent": "Learning Agent",
            }

            claim["feedback_data"] = feedback_data
            claim["feedback"] = feedback_payload
            claim["feedback_captured"] = True
            claim["feedback_duration_seconds"] = duration_seconds

            # ---------------------------------------------------
            # Step 5: Update metrics
            # ---------------------------------------------------
            print("➡️ [5] Updating feedback metrics...")

            update_metrics(
                event_type="feedback_completed",
                claim_id=claim_id,
                agent="FEEDBACK",
                payer=claim.get("payer"),
                risk_score=risk_score,
                latency=duration_seconds,
                status="COMPLETED",
            )

            print("✅ Feedback metrics updated")

            # ---------------------------------------------------
            # Step 6: Send frontend event
            # ---------------------------------------------------
            print("➡️ [6] Sending feedback event to frontend...")

            await manager.send_event(
                "feedback",
                "completed",
                feedback_payload,
            )

            print("✅ Feedback event sent")
            print(f"⏱️ Feedback duration: {duration_seconds}s")
            print("⏭️ Next agent: Learning Agent")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "feedback_logged": True,
                "feedback_data": feedback_data,
                "feedback": feedback_payload,
                "pipeline": {
                    "steps": {
                        "feedback_captured": True
                    }
                },
                "stage": "feedback_completed",
                "status": "COMPLETED",
                "duration_seconds": duration_seconds,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [FeedbackLoopAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Feedback duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            logger.exception("Feedback Loop Agent failed")

            await manager.send_event("feedback", "failed", {
                "claim_id": claim_id,
                "submission_id": submission_id,
                "error": str(error),
                "duration_seconds": duration_seconds,
                "next_agent": "Learning Agent",
            })

            update_metrics(
                event_type="feedback_failed",
                claim_id=claim_id,
                agent="FEEDBACK",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            return {
                "claim": claim,
                "feedback_logged": False,
                "pipeline": {
                    "steps": {
                        "feedback_captured": False
                    }
                },
                "stage": "feedback_failed",
                "status": "FAILED",
                "error": str(error),
                "duration_seconds": duration_seconds,
            }

    def _normalize_score(self, value):
        try:
            score = float(value or 0)
        except (TypeError, ValueError):
            score = 0

        if score > 1:
            score = score / 100

        return max(0.0, min(1.0, score))
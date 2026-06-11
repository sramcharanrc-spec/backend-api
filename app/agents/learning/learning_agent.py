# from app.agents.base.base_agent import BaseAgent
# import logging
# import time
# from app.services.learning_service import LearningService
# from app.services.analytics_service import update_metrics
# from app.db.database import get_db

# logger = logging.getLogger(__name__)

# class LearningAgent(BaseAgent):
#     """
#     Learning Agent

#     Responsibilities:
#     * analyze previous denials
#     * analyze corrections
#     * improve validation heuristics
#     * generate confidence metrics
#     * capture AI improvement signals
#     """

#     async def run(self, claim):
#         start_time = time.time()
#         claim = claim or {}
#         logger.info("🧠 [LEARNING] Learning analysis started")

#         # Analyze feedback
#         feedback = claim.get("feedback_data", {})
#         denial_reason = feedback.get("denial_reason")
#         corrections = feedback.get("validation_corrections", [])
#         risk_score = feedback.get("risk_score", 0)

#         # Update patterns
#         metrics_data = {
#             "claim_id": claim.get("claim_id"),
#             "denial_patterns": [denial_reason] if denial_reason else [],
#             "correction_history": corrections,
#             "confidence_trends": self._calculate_confidence(risk_score),
#             "improvement_signals": {"risk_reduction": 1 - risk_score if risk_score else 0}
#         }

#         # Store metrics
#         db = next(get_db())
#         service = LearningService(db)
#         service.create_metrics(metrics_data)
#         logger.info(f"💾 [LEARNING] Metrics stored for claim {claim.get('claim_id')}")

#         update_metrics(
#             event_type="learning_completed",
#             claim_id=claim.get("claim_id"),
#             agent="LEARNING",
#             payer=claim.get("payer"),
#             risk_score=risk_score,
#             latency=time.time() - start_time,
#             status="COMPLETED",
#         )

#         return {
#             "claim": claim,
#             "learning_updated": True,
#             "patterns": metrics_data
#         }

#     def _calculate_confidence(self, risk_score):
#         """Calculate confidence based on risk score"""
#         # Placeholder
#         return {"confidence": 1 - risk_score if risk_score else 0.8}


import logging
import time

from app.agents.base.base_agent import BaseAgent
from app.services.learning_service import LearningService
from app.services.analytics_service import update_metrics
from app.db.database import get_db
from app.websocket.manager import manager
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event

logger = logging.getLogger(__name__)


class LearningAgent(BaseAgent):
    """
    Learning Agent

    Responsibilities:
    - Analyze denials, corrections, validation failures, and payment outcomes
    - Capture improvement signals
    - Store learning metrics
    - Provide frontend-visible learning summary
    """

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}

        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "=" * 80)
        print("🧠 [LearningAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        logger.info("🧠 [LEARNING] Learning analysis started")

        await send_pipeline_event(
            manager,
            topic="learning",
            action="running",
            claim_id=claim_id,
            stage="LEARNING",
            status="RUNNING",
            progress=94,
            current_stage="LEARNING",
            current_agent="LearningAgent",
            active_step="learning",
            pipeline_state="LEARNING_RUNNING",
            pipeline_status="RUNNING",
            review_required=False,
            approval_required=False,
            pipeline_paused=False,
            message="Learning Agent started",
            claim=claim,
        )

        try:
            # ---------------------------------------------------
            # Step 1: Collect learning inputs
            # ---------------------------------------------------
            print("➡️ [1] Collecting learning inputs...")

            feedback = claim.get("feedback_data") or {}
            validation = claim.get("validation") or {}
            compliance = claim.get("compliance") or {}
            denial = claim.get("denial") or {}
            payment = claim.get("payment_result") or claim.get("payment") or {}

            denial_reason = (
                feedback.get("denial_reason")
                or denial.get("reason")
                or denial.get("root_cause")
            )

            denial_code = (
                denial.get("denial_code")
                or claim.get("denial_code")
            )

            corrections = (
                feedback.get("validation_corrections")
                or denial.get("suggested_corrections")
                or []
            )

            risk_score = self._normalize_score(
                feedback.get("risk_score")
                or compliance.get("risk_score")
                or validation.get("risk_score")
                or claim.get("risk_score")
                or 0
            )

            validation_score = self._normalize_score(
                validation.get("validation_score")
                or claim.get("validation_score")
                or 0
            )

            payment_status = (
                payment.get("payment_status")
                or claim.get("payment_status")
            )

            payment_rate = self._normalize_score(
                payment.get("payment_rate")
                or 0
            )

            print(f"📌 Denial reason: {denial_reason}")
            print(f"📌 Denial code: {denial_code}")
            print(f"📊 Risk score: {risk_score}")
            print(f"📊 Validation score: {validation_score}")
            print(f"💳 Payment status: {payment_status}")
            print(f"💳 Payment rate: {payment_rate}")

            # ---------------------------------------------------
            # Step 2: Build learning metrics
            # ---------------------------------------------------
            print("➡️ [2] Building learning metrics...")

            confidence = self._calculate_confidence(risk_score)

            improvement_signals = {
                "risk_reduction": round(1 - risk_score, 2),
                "validation_quality": validation_score,
                "payment_success": payment_status == "paid",
                "denial_detected": bool(denial.get("denial_found")),
                "appeal_generated": bool(denial.get("appeal_text") or denial.get("appeal")),
                "corrections_available": bool(corrections),
            }

            metrics_data = {
                "claim_id": claim_id,
                "denial_patterns": [denial_reason] if denial_reason else [],
                "denial_code": denial_code,
                "correction_history": corrections,
                "confidence_trends": confidence,
                "improvement_signals": improvement_signals,
                "validation_learning": {
                    "validation_status": validation.get("status"),
                    "validation_score": validation_score,
                    "failed_rules": validation.get("failed_rules", []),
                    "critical_errors": validation.get("critical_errors", []),
                },
                "compliance_learning": {
                    "compliance_status": compliance.get("compliance_status"),
                    "severity": compliance.get("severity"),
                    "rule": compliance.get("rule"),
                    "risk_score": compliance.get("risk_score"),
                },
                "denial_learning": {
                    "denial_found": denial.get("denial_found", False),
                    "denial_code": denial_code,
                    "denial_type": denial.get("denial_type"),
                    "root_cause": denial.get("root_cause"),
                    "suggestions_count": len(corrections) if isinstance(corrections, list) else 0,
                },
                "payment_learning": {
                    "payment_status": payment_status,
                    "payment_rate": payment_rate,
                    "underpaid": payment_status == "underpaid",
                    "denied": payment_status == "denied",
                },
            }

            print("✅ Learning metrics built")
            print(f"📊 Confidence: {confidence}")
            print(f"📈 Improvement signals: {improvement_signals}")

            # ---------------------------------------------------
            # Step 3: Store metrics
            # ---------------------------------------------------
            print("➡️ [3] Storing learning metrics...")

            persistence_status = "SUCCESS"
            persistence_error = None
            db = None

            try:
                db_gen = get_db()
                db = next(db_gen)
                service = LearningService(db)
                service.create_metrics(metrics_data)
                print(f"✅ Learning metrics stored for claim {claim_id}")
                logger.info(f"💾 [LEARNING] Metrics stored for claim {claim_id}")

            except Exception as error:
                logger.exception(
                    "Learning metrics persistence failed for claim %s",
                    claim_id,
                )
                persistence_status = "FAILED"
                persistence_error = str(error)
                print(f"⚠️ Learning metrics persistence failed: {persistence_error}")

            finally:
                if db is not None:
                    db.close()

            # ---------------------------------------------------
            # Step 4: Final payload
            # ---------------------------------------------------
            duration_seconds = round(time.time() - start_time, 2)
            learning_status = (
                "COMPLETED"
                if persistence_status == "SUCCESS"
                else "COMPLETED_WITH_WARNINGS"
            )

            learning_payload = {
                "claim_id": claim_id,
                "agent": "LearningAgent",
                "status": "COMPLETED",
                "learning_status": learning_status,
                "persistence_status": persistence_status,
                "persistence_error": persistence_error,
                "learning_updated": True,
                "patterns": metrics_data,
                "confidence": confidence.get("confidence"),
                "confidence_percent": round(confidence.get("confidence", 0) * 100),
                "risk_score": risk_score,
                "risk_score_percent": round(risk_score * 100),
                "improvement_signals": improvement_signals,
                "duration_seconds": duration_seconds,
                "current_stage": "LEARNING",
                "current_agent": "LearningAgent",
                "active_step": "learning",
                "pipeline_state": "LEARNING_COMPLETED",
                "pipeline_status": "COMPLETED",
                "progress": 94,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "next_agent": "Analytics Agent",
            }

            claim["learning"] = learning_payload
            claim["learning_updated"] = True
            claim["learning_duration_seconds"] = duration_seconds

            agent_detail = self.build_agent_detail(
                "learning",
                status=(
                    "COMPLETED"
                    if learning_status == "COMPLETED"
                    else "WARNING"
                ),
                active_step="Learning metrics captured",
                message=(
                    "Learning metrics captured"
                    if persistence_status == "SUCCESS"
                    else "Learning completed with persistence warning"
                ),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=True,
                score=learning_payload.get("confidence_percent"),
                risk_score=risk_score,
                risk_score_percent=learning_payload.get("risk_score_percent"),
                warnings=[persistence_error] if persistence_error else [],
                output=learning_payload,
                next_agent="Analytics Agent",
            )
            self.apply_agent_detail(
                claim,
                "learning",
                agent_detail,
                step_completed=True,
                result_status="COMPLETED",
            )
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="LEARNING",
                status="COMPLETED",
                progress=94,
                current_stage="LEARNING",
                current_agent="LearningAgent",
                active_step="learning",
                pipeline_state="LEARNING_COMPLETED",
                pipeline_status="COMPLETED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message="Learning completed",
            )
            claim["pipeline"]["steps"]["learning_updated"] = True
            claim["pipeline"]["steps"]["learning_done"] = True

            # ---------------------------------------------------
            # Step 5: Update metrics service
            # ---------------------------------------------------
            print("➡️ [4] Updating analytics metrics...")

            update_metrics(
                event_type="learning_completed",
                claim_id=claim_id,
                agent="LEARNING",
                payer=claim.get("payer"),
                risk_score=risk_score,
                latency=duration_seconds,
                status=learning_status,
            )

            print("✅ Analytics metrics updated")

            # ---------------------------------------------------
            # Step 6: Send frontend event
            # ---------------------------------------------------
            print("➡️ [5] Sending learning event to frontend...")

            await send_pipeline_event(
                manager,
                topic="learning",
                action="completed",
                claim_id=claim_id,
                stage="LEARNING",
                status="COMPLETED",
                progress=94,
                current_stage="LEARNING",
                current_agent="LearningAgent",
                active_step="learning",
                pipeline_state="LEARNING_COMPLETED",
                pipeline_status="COMPLETED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message="Learning completed",
                claim=claim,
                extra={
                    "learning": learning_payload,
                    "learning_updated": True,
                    "patterns": metrics_data,
                    "agent_detail": agent_detail,
                },
            )

            print("✅ Learning event sent")
            print(f"⏱️ Learning duration: {duration_seconds}s")
            print("⏭️ Next agent: Analytics Agent")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "learning_updated": True,
                "patterns": metrics_data,
                "learning": learning_payload,
                "pipeline": claim.get("pipeline", {}),
                "stage": "learning_completed",
                "status": "COMPLETED",
                "learning_status": learning_status,
                "pipeline_state": "LEARNING_COMPLETED",
                "pipeline_status": "COMPLETED",
                "current_stage": "LEARNING",
                "current_agent": "LearningAgent",
                "active_step": "learning",
                "duration_seconds": duration_seconds,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [LearningAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Learning duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            logger.exception("Learning Agent failed")

            failure_payload = {
                "claim_id": claim_id,
                "error": str(error),
                "duration_seconds": duration_seconds,
                "current_stage": "LEARNING",
                "current_agent": "LearningAgent",
                "active_step": "learning",
                "pipeline_state": "LEARNING_FAILED",
                "pipeline_status": "FAILED",
                "progress": 94,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "next_agent": "Analytics Agent",
            }
            agent_detail = self.build_agent_detail(
                "learning",
                status="FAILED",
                active_step="Learning processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output=failure_payload,
                next_agent="Analytics Agent",
            )
            self.apply_agent_detail(
                claim,
                "learning",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="LEARNING",
                status="FAILED",
                progress=94,
                current_stage="LEARNING",
                current_agent="LearningAgent",
                active_step="learning",
                pipeline_state="LEARNING_FAILED",
                pipeline_status="FAILED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=str(error),
            )
            claim["pipeline"]["steps"]["learning_updated"] = False
            claim["pipeline"]["steps"]["learning_done"] = False

            await send_pipeline_event(
                manager,
                topic="learning",
                action="failed",
                claim_id=claim_id,
                stage="LEARNING",
                status="FAILED",
                progress=94,
                current_stage="LEARNING",
                current_agent="LearningAgent",
                active_step="learning",
                pipeline_state="LEARNING_FAILED",
                pipeline_status="FAILED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=str(error),
                claim=claim,
                extra={
                    **failure_payload,
                    "learning_updated": False,
                    "agent_detail": agent_detail,
                },
            )

            update_metrics(
                event_type="learning_failed",
                claim_id=claim_id,
                agent="LEARNING",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            return {
                "claim": claim,
                "learning_updated": False,
                "pipeline": claim.get("pipeline", {}),
                "stage": "learning_failed",
                "status": "FAILED",
                "pipeline_state": "LEARNING_FAILED",
                "pipeline_status": "FAILED",
                "current_stage": "LEARNING",
                "current_agent": "LearningAgent",
                "active_step": "learning",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "agent_detail": agent_detail,
            }

    def _calculate_confidence(self, risk_score):
        risk_score = self._normalize_score(risk_score)
        confidence = round(1 - risk_score, 2)

        return {
            "confidence": confidence,
            "confidence_percent": round(confidence * 100)
        }

    def _normalize_score(self, value):
        try:
            score = float(value or 0)
        except (TypeError, ValueError):
            score = 0

        if score > 1:
            score = score / 100

        return max(0.0, min(1.0, score))

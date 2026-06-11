# from app.agents.base import BaseAgent
# from app.lambdas.analytics_agent.analytics import analytics_dashboard

# class AnalyticsAgent(BaseAgent):
#     name = "Analytics Agent"

#     def run(self, payload: dict):
#         return analytics_dashboard()


import time
import logging

from app.agents.base.base_agent import BaseAgent
from app.lambdas.analytics_agent.analytics import analytics_dashboard
from app.services.analytics_service import update_metrics
from app.websocket.manager import manager
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event

logger = logging.getLogger(__name__)


class AnalyticsAgent(BaseAgent):
    name = "Analytics Agent"

    async def run(self, state):
        start_time = time.time()

        state = state or {}

        claim = (
            state.get("claim")
            or state.get("claim_data")
            or state
            or {}
        )

        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "=" * 80)
        print("📊 [AnalyticsAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming state keys: {list(state.keys()) if isinstance(state, dict) else []}")
        print(f"📥 Incoming claim keys: {list(claim.keys()) if isinstance(claim, dict) else []}")
        print("=" * 80)

        await send_pipeline_event(
            manager,
            topic="analytics",
            action="running",
            claim_id=claim_id,
            stage="ANALYTICS",
            status="RUNNING",
            progress=100,
            current_stage="ANALYTICS",
            current_agent="AnalyticsAgent",
            active_step="analytics",
            pipeline_state="ANALYTICS_RUNNING",
            pipeline_status="RUNNING",
            review_required=False,
            approval_required=False,
            pipeline_paused=False,
            message="Analytics Agent started",
            claim=claim,
        )

        try:
            print("➡️ [1] Reading pipeline signals...")

            validation = claim.get("validation") or {}
            compliance = claim.get("compliance") or {}
            denial = claim.get("denial") or {}
            payment = claim.get("payment_result") or claim.get("payment") or {}
            learning = claim.get("learning") or {}
            feedback = claim.get("feedback_data") or {}

            payment_status = (
                payment.get("payment_status")
                or claim.get("payment_status")
            )

            denial_found = denial.get("denial_found", False)

            validation_score = (
                validation.get("validation_score")
                or claim.get("validation_score")
                or 0
            )

            risk_score = (
                compliance.get("risk_score")
                or validation.get("risk_score")
                or denial.get("risk_score")
                or claim.get("risk_score")
                or 0
            )

            print(f"📊 Validation score: {validation_score}")
            print(f"📊 Risk score: {risk_score}")
            print(f"🚫 Denial found: {denial_found}")
            print(f"💳 Payment status: {payment_status}")

            # ---------------------------------------------------
            # Dashboard data
            # ---------------------------------------------------
            print("➡️ [2] Generating analytics dashboard...")

            dashboard = analytics_dashboard()

            print("✅ Analytics dashboard generated")

            # ---------------------------------------------------
            # Claim-level analytics summary
            # ---------------------------------------------------
            print("➡️ [3] Building claim analytics summary...")

            analytics_summary = {
                "claim_id": claim_id,
                "validation_score": validation_score,
                "risk_score": risk_score,
                "denial_found": denial_found,
                "denial_code": denial.get("denial_code"),
                "payment_status": payment_status,
                "payment_rate_percent": payment.get("payment_rate_percent"),
                "compliance_status": compliance.get("compliance_status"),
                "learning_updated": bool(learning),
                "feedback_captured": bool(feedback),
            }

            duration_seconds = round(time.time() - start_time, 2)

            analytics_payload = {
                "claim_id": claim_id,
                "agent": "AnalyticsAgent",
                "status": "COMPLETED",
                "analytics_done": True,
                "summary": analytics_summary,
                "dashboard": dashboard,
                "duration_seconds": duration_seconds,
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "pipeline_state": "ANALYTICS_COMPLETED",
                "pipeline_status": "COMPLETED",
                "progress": 100,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "next_agent": "Finish",
            }

            claim["analytics"] = analytics_payload
            claim["analytics_done"] = True
            claim["analytics_duration_seconds"] = duration_seconds
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="ANALYTICS",
                status="COMPLETED",
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state="ANALYTICS_COMPLETED",
                pipeline_status="COMPLETED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message="Analytics completed",
            )
            claim["pipeline"]["steps"]["analytics_done"] = True

            print("✅ Analytics summary built")
            print(f"⏱️ Analytics duration: {duration_seconds}s")

            # ---------------------------------------------------
            # Metrics
            # ---------------------------------------------------
            print("➡️ [4] Updating analytics metrics...")

            update_metrics(
                event_type="analytics_completed",
                claim_id=claim_id,
                agent="ANALYTICS",
                payer=claim.get("payer"),
                risk_score=risk_score,
                latency=duration_seconds,
                status="COMPLETED",
            )

            print("✅ Analytics metrics updated")

            # ---------------------------------------------------
            # Frontend events
            # ---------------------------------------------------
            print("➡️ [5] Sending analytics event to frontend...")

            await send_pipeline_event(
                manager,
                topic="analytics",
                action="completed",
                claim_id=claim_id,
                stage="ANALYTICS",
                status="COMPLETED",
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state="ANALYTICS_COMPLETED",
                pipeline_status="COMPLETED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message="Analytics completed",
                claim=claim,
                extra={
                    "analytics": analytics_payload,
                    "analytics_done": True,
                },
            )

            paid_amount = (
                claim.get("paid_amount")
                or claim.get("payment_amount")
                or claim.get("received_amount")
                or (payment.get("paid_amount") if isinstance(payment, dict) else None)
                or (payment.get("received_amount") if isinstance(payment, dict) else None)
            )
            try:
                has_paid_amount = float(paid_amount or 0) > 0
            except (TypeError, ValueError):
                has_paid_amount = False

            final_status = "PAID" if str(payment_status or "").lower() == "paid" or has_paid_amount else "COMPLETED"

            if final_status == "PAID":
                claim["status"] = "PAID"
                apply_pipeline_patch(
                    claim,
                    claim_id=claim_id,
                    stage="ANALYTICS",
                    status="PAID",
                    progress=100,
                    current_stage="ANALYTICS",
                    current_agent="AnalyticsAgent",
                    active_step="analytics",
                    pipeline_state="COMPLETED",
                    pipeline_status="COMPLETED",
                    review_required=False,
                    approval_required=False,
                    pipeline_paused=False,
                    message="Claim paid and pipeline completed",
                )
                claim["pipeline"]["steps"]["analytics_done"] = True

                await send_pipeline_event(
                    manager,
                    topic="analytics",
                    action="paid",
                    claim_id=claim_id,
                    stage="ANALYTICS",
                    status="PAID",
                    progress=100,
                    current_stage="ANALYTICS",
                    current_agent="AnalyticsAgent",
                    active_step="analytics",
                    pipeline_state="COMPLETED",
                    pipeline_status="COMPLETED",
                    review_required=False,
                    approval_required=False,
                    pipeline_paused=False,
                    message="Claim paid and pipeline completed",
                    claim=claim,
                    extra={
                        "analytics": analytics_payload,
                        "analytics_done": True,
                        "payment_status": payment_status,
                        "paid_amount": paid_amount,
                    },
                )

            print("✅ Analytics event sent")
            print("🏁 [AnalyticsAgent] COMPLETED")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "analytics": analytics_payload,
                "dashboard": dashboard,
                "pipeline": claim.get("pipeline", {}),
                "analytics_done": True,
                "stage": "analytics_completed",
                "status": final_status,
                "pipeline_state": claim.get("pipeline_state"),
                "pipeline_status": claim.get("pipeline_status"),
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "duration_seconds": duration_seconds,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [AnalyticsAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Analytics duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            logger.exception("Analytics Agent failed")

            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="ANALYTICS",
                status="FAILED",
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state="ANALYTICS_FAILED",
                pipeline_status="FAILED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=str(error),
            )
            claim["pipeline"]["steps"]["analytics_done"] = False

            await send_pipeline_event(
                manager,
                topic="analytics",
                action="failed",
                claim_id=claim_id,
                stage="ANALYTICS",
                status="FAILED",
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state="ANALYTICS_FAILED",
                pipeline_status="FAILED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=str(error),
                claim=claim,
                extra={
                    "error": str(error),
                    "duration_seconds": duration_seconds,
                    "next_agent": "Finish",
                },
            )

            update_metrics(
                event_type="analytics_failed",
                claim_id=claim_id,
                agent="ANALYTICS",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "analytics_done": False,
                "stage": "analytics_failed",
                "status": "FAILED",
                "pipeline_state": "ANALYTICS_FAILED",
                "pipeline_status": "FAILED",
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "error": str(error),
                "duration_seconds": duration_seconds,
            }

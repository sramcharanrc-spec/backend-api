import time

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event


class AnalyticsAgent(BaseAgent):

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}
        claim_id = claim.get("claim_id", "UNKNOWN")
        trace_id = await self.log_start("AnalyticsAgent", claim_id)

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
            extra={"trace_id": trace_id, "agent": "AnalyticsAgent"},
        )

        try:
            denial = claim.get("denial_risk") or {}
            await self.log_step(
                "AnalyticsAgent",
                "Building analytics summary",
                {
                    "risk_score": denial.get("risk_score"),
                    "total_charge": claim.get("total_charge"),
                    "service_count": len(claim.get("services", [])),
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            analytics_payload = {
                "risk_score": float(denial.get("risk_score") or 0),
                "total_charge": claim.get("total_charge"),
                "service_count": len(claim.get("services", [])),
                "processed": True,
                "duration_seconds": round(time.time() - start_time, 2),
                "trace_id": trace_id,
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "pipeline_state": "ANALYTICS_COMPLETED",
                "pipeline_status": "COMPLETED",
                "progress": 100,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
            }
            claim["analytics"] = analytics_payload
            claim["analytics_done"] = True

            duration_seconds = analytics_payload["duration_seconds"]
            agent_detail = self.build_agent_detail(
                "analytics",
                status="COMPLETED",
                active_step="Analytics summary completed",
                message="Analytics summary completed",
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=True,
                risk_score=analytics_payload.get("risk_score"),
                output=analytics_payload,
                next_agent=None,
            )
            self.apply_agent_detail(
                claim,
                "analytics",
                agent_detail,
                step_completed=True,
                result_status="COMPLETED",
            )
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
                    "agent_detail": agent_detail,
                    "trace_id": trace_id,
                },
            )

            payment = claim.get("payment_result") or claim.get("payment") or {}
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

            payment_financials = payment.get("financials") if isinstance(payment, dict) else {}
            if not isinstance(payment_financials, dict):
                payment_financials = {}

            payment_status = str(
                claim.get("payment_status")
                or payment.get("payment_status")
                or payment_financials.get("payment_status")
                or payment_financials.get("status")
                or claim.get("pipeline_status")
                or ""
            ).strip().lower()

            reconciliation_statuses = {
                "underpaid",
                "overpaid",
                "paid_with_adjustment",
                "payment_reconciliation_required",
            }

            print("🧾 [AnalyticsAgent DEBUG] claim.payment_status =", claim.get("payment_status"), flush=True)
            print("🧾 [AnalyticsAgent DEBUG] claim.pipeline_status =", claim.get("pipeline_status"), flush=True)
            print("🧾 [AnalyticsAgent DEBUG] payment_status normalized =", payment_status, flush=True)
            print("🧾 [AnalyticsAgent DEBUG] has_paid_amount =", has_paid_amount, flush=True)


            if payment_status in reconciliation_statuses:
                final_status = "PAYMENT_RECONCILIATION_REQUIRED"
                final_pipeline_state = "PAYMENT_RECONCILIATION_REQUIRED"
                final_pipeline_status = payment_status.upper()
                final_message = f"Payment reconciliation required: {payment_status}"
                final_action = "payment_reconciliation_required"

            elif payment_status in {"denied", "payment_denied"}:
                final_status = "PAYMENT_DENIED"
                final_pipeline_state = "PAYMENT_DENIED"
                final_pipeline_status = "DENIED"
                final_message = "Payment denied"
                final_action = "payment_denied"

            elif payment_status == "paid":
                final_status = "PAID"
                final_pipeline_state = "COMPLETED"
                final_pipeline_status = "COMPLETED"
                final_message = "Claim paid and pipeline completed"
                final_action = "paid"

            elif has_paid_amount:
                final_status = "COMPLETED"
                final_pipeline_state = claim.get("pipeline_state") or "COMPLETED"
                final_pipeline_status = claim.get("pipeline_status") or "COMPLETED"
                final_message = "Analytics completed with payment amount present"
                final_action = "completed"

            else:
                final_status = "COMPLETED"
                final_pipeline_state = "COMPLETED"
                final_pipeline_status = "COMPLETED"
                final_message = "Analytics completed"
                final_action = "completed"

            claim["status"] = final_status

            if final_status in {
                "PAID",
                "PAYMENT_RECONCILIATION_REQUIRED",
                "PAYMENT_DENIED",
            }:
                claim["stage"] = "FINISH"

            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="ANALYTICS",
                status=final_status,
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state=final_pipeline_state,
                pipeline_status=final_pipeline_status,
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=final_message,
            )

            claim["pipeline"]["steps"]["analytics_done"] = True

            await send_pipeline_event(
                manager,
                topic="analytics",
                action=final_action,
                claim_id=claim_id,
                stage="ANALYTICS",
                status=final_status,
                progress=100,
                current_stage="ANALYTICS",
                current_agent="AnalyticsAgent",
                active_step="analytics",
                pipeline_state=final_pipeline_state,
                pipeline_status=final_pipeline_status,
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=final_message,
                claim=claim,
                extra={
                    "analytics": analytics_payload,
                    "analytics_done": True,
                    "payment_status": payment_status,
                    "paid_amount": paid_amount,
                    "agent_detail": agent_detail,
                    "trace_id": trace_id,
                },
            )            

            await self.log_end(
                "AnalyticsAgent",
                "SUCCESS",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "stage": "analytics_done",
                "trace_id": trace_id,
                "analytics": analytics_payload,
                "status": final_status,
                "pipeline_state": claim.get("pipeline_state"),
                "pipeline_status": claim.get("pipeline_status"),
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "duration_seconds": duration_seconds,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)
            failure_payload = {
                "claim_id": claim_id,
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "current_stage": "ANALYTICS",
                "current_agent": "AnalyticsAgent",
                "active_step": "analytics",
                "pipeline_state": "ANALYTICS_FAILED",
                "pipeline_status": "FAILED",
                "progress": 100,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
            }
            agent_detail = self.build_agent_detail(
                "analytics",
                status="FAILED",
                active_step="Analytics processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output=failure_payload,
                next_agent=None,
            )
            self.apply_agent_detail(
                claim,
                "analytics",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )
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
                    **failure_payload,
                    "agent_detail": agent_detail,
                },
            )
            await self.log_error(
                "AnalyticsAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            await self.log_end(
                "AnalyticsAgent",
                "FAILED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            raise

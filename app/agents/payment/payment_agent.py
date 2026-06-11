import time

from app.agents.base.base_agent import BaseAgent
from app.rcm.edi_responses import generate_era_835
from app.intake.db_service import update_record_status
from app.services.audit_service import log_audit
from app.services.analytics_service import update_metrics
from app.websocket.manager import manager
from app.rcm.alerts import detect_underpayment
from app.utils.pipeline_events import apply_pipeline_patch, send_pipeline_event


def _claim_source_text(claim: dict) -> str:
    source_file = claim.get("source_file") or {}

    parts = [
        claim.get("claim_id"),
        claim.get("id"),
        claim.get("filename"),
        claim.get("file_name"),
        claim.get("source"),
        claim.get("document_type"),
        claim.get("form_type"),
        source_file.get("key") if isinstance(source_file, dict) else None,
        source_file.get("s3_uri") if isinstance(source_file, dict) else None,
        claim.get("payment_scenario"),
        claim.get("payment_test_scenario"),
        claim.get("test_scenario"),
        claim.get("scenario"),
    ]

    return " ".join(str(part or "") for part in parts).lower()


def detect_payment_test_scenario(claim: dict) -> str:
    """
    Detect local/demo payment scenario from filename or metadata.

    Supported filename examples:
    - 02_CMS1500_Payment_Underpayment.pdf
    - 03_CMS1500_Payment_Overpayment.pdf
    - 04_CMS1500_Payment_Adjustment.pdf
    - 05_CMS1500_Payment_Denial.pdf
    """
    text = _claim_source_text(claim)

    if "underpayment" in text or "under_paid" in text or "underpaid" in text:
        return "UNDERPAYMENT"

    if "overpayment" in text or "over_paid" in text or "overpaid" in text:
        return "OVERPAYMENT"

    if "adjustment" in text or "paid_with_adjustment" in text:
        return "ADJUSTMENT"

    if "payment_denial" in text or "payment-denial" in text:
        return "DENIAL"

    # Keep this specific so normal denial_ai files do not trigger payment denial.
    if "payment" in text and "denial" in text:
        return "DENIAL"

    return "NORMAL"


def build_test_payment_financials(claim: dict) -> dict:
    expected_amount = _safe_float(
        claim.get("expected_reimbursement")
        or claim.get("expected_amount")
        or claim.get("total_charge")
        or claim.get("charge_amount")
        or 0.0
    )

    scenario = detect_payment_test_scenario(claim)

    if scenario == "UNDERPAYMENT":
        received_amount = round(expected_amount * 0.80, 2)
        adjustment = round(expected_amount - received_amount, 2)

        return {
            "scenario": scenario,
            "expected_amount": expected_amount,
            "received_amount": received_amount,
            "paid_amount": received_amount,
            "adjustment": adjustment,
            "patient_responsibility": 0.0,
            "variance": round(received_amount - expected_amount, 2),
            "payment_rate": round(received_amount / expected_amount, 4) if expected_amount else 0.0,
            "payment_rate_percent": 80,
            "payment_status": "underpaid",
            "era_status": "PAID",
            "reason": "CO-45 Contractual adjustment / reduced allowed amount",
            "underpayment_alert": True,
            "overpayment_alert": False,
            "denial_at_payment": False,
        }

    if scenario == "OVERPAYMENT":
        received_amount = round(expected_amount * 1.20, 2)
        adjustment = 0.0

        return {
            "scenario": scenario,
            "expected_amount": expected_amount,
            "received_amount": received_amount,
            "paid_amount": received_amount,
            "adjustment": adjustment,
            "patient_responsibility": 0.0,
            "variance": round(received_amount - expected_amount, 2),
            "payment_rate": round(received_amount / expected_amount, 4) if expected_amount else 0.0,
            "payment_rate_percent": 120,
            "payment_status": "overpaid",
            "era_status": "PAID",
            "reason": "Overpayment detected against expected reimbursement",
            "underpayment_alert": False,
            "overpayment_alert": True,
            "denial_at_payment": False,
        }

    if scenario == "ADJUSTMENT":
        received_amount = round(expected_amount * 0.70, 2)
        patient_responsibility = round(expected_amount * 0.10, 2)
        adjustment = round(expected_amount - received_amount - patient_responsibility, 2)

        return {
            "scenario": scenario,
            "expected_amount": expected_amount,
            "received_amount": received_amount,
            "paid_amount": received_amount,
            "adjustment": adjustment,
            "patient_responsibility": patient_responsibility,
            "variance": round(received_amount + patient_responsibility - expected_amount, 2),
            "payment_rate": round(received_amount / expected_amount, 4) if expected_amount else 0.0,
            "payment_rate_percent": 70,
            "payment_status": "paid_with_adjustment",
            "era_status": "PAID",
            "reason": "Partial payer payment with contractual adjustment and patient responsibility",
            "underpayment_alert": False,
            "overpayment_alert": False,
            "denial_at_payment": False,
        }

    if scenario == "DENIAL":
        received_amount = 0.0
        adjustment = expected_amount

        return {
            "scenario": scenario,
            "expected_amount": expected_amount,
            "received_amount": received_amount,
            "paid_amount": received_amount,
            "adjustment": adjustment,
            "patient_responsibility": 0.0,
            "variance": round(received_amount - expected_amount, 2),
            "payment_rate": 0.0,
            "payment_rate_percent": 0,
            "payment_status": "denied",
            "era_status": "DENIED",
            "reason": "CO-16 Claim/service lacks required information",
            "denial_code": "CO-16",
            "underpayment_alert": False,
            "overpayment_alert": False,
            "denial_at_payment": True,
        }

    received_amount = expected_amount

    return {
        "scenario": scenario,
        "expected_amount": expected_amount,
        "received_amount": received_amount,
        "paid_amount": received_amount,
        "adjustment": 0.0,
        "patient_responsibility": 0.0,
        "variance": 0.0,
        "payment_rate": 1.0 if expected_amount else 0.0,
        "payment_rate_percent": 100 if expected_amount else 0,
        "payment_status": "paid",
        "era_status": "PAID",
        "reason": None,
        "underpayment_alert": False,
        "overpayment_alert": False,
        "denial_at_payment": False,
    }

def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = (
                value
                .replace("$", "")
                .replace(",", "")
                .replace("USD", "")
                .strip()
            )

        if value == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default



class PaymentAgent(BaseAgent):

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}

        claim_id = claim.get("claim_id", "UNKNOWN")
        trace_id = await self.log_start("PaymentAgent", claim_id)

        print("\n" + "=" * 80)
        print("💳 [PaymentAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"🔎 Trace ID: {trace_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        await send_pipeline_event(
            manager,
            topic="payment",
            action="running",
            claim_id=claim_id,
            stage="PAYMENT",
            status="RUNNING",
            progress=88,
            current_stage="PAYMENT",
            current_agent="PaymentAgent",
            active_step="payment",
            pipeline_state="PAYMENT_RUNNING",
            pipeline_status="RUNNING",
            review_required=False,
            approval_required=False,
            pipeline_paused=False,
            message="Payment Agent started",
            claim=claim,
            extra={"trace_id": trace_id},
        )

        try:
            # ---------------------------------------------------
            # Step 1: Read payment inputs
            # ---------------------------------------------------
            print("➡️ [1] Reading payment inputs...")

            total = _safe_float(
                claim.get("total_charge")
                or claim.get("claim_amount")
                or claim.get("billed_amount")
                or claim.get("charge_amount")
                or claim.get("amount"),
                0.0,
            )

            if total <= 0:
                services = claim.get("services") or []
                total = sum(
                    _safe_float(
                        service.get("charge_amount")
                        or service.get("charge")
                        or service.get("billed_amount"),
                        0.0,
                    )
                    for service in services
                    if isinstance(service, dict)
                )

            test_financials = build_test_payment_financials(
                {
                    **claim,
                    "total_charge": total,
                }
            )

            scenario = test_financials["scenario"]
            received = test_financials["received_amount"]

            print(f"🧪 Payment test scenario detected: {scenario}")

            submission_id = claim.get("submission_id")

            ack_status = (
                claim.get("ack", {})
                .get("ack_277", {})
                .get("status")
            )

            print(f"📤 Submission ID: {submission_id}")
            print(f"💰 Expected amount: {total}")
            print(f"📩 ACK status: {ack_status}")

            await self.log_step(
                "PaymentAgent",
                "Checking ACK status",
                {
                    "submission_id": submission_id,
                    "expected_amount": total,
                    "ack_status": ack_status,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            if not submission_id:
                raise ValueError("Missing submission_id for payment processing")

            if total <= 0:
                print("⚠️ Total charge is zero or missing")

            print(f"💰 Total billed amount: {total}")
            print(f"💵 Received payment amount: {received}")

            # ---------------------------------------------------
            # Step 2: Handle rejected ACK
            # ---------------------------------------------------
            era = None

            if ack_status == "REJECTED":
                print("⛔ ACK status is REJECTED. Marking payment as denied.")

                from app.rcm.submission import record_denial

                record_denial(
                    submission_id,
                    "D001",
                    "Rejected by payer",
                )

                claim["status"] = "denied"
                claim["payment_status"] = "denied"

                received = 0.0
                adjustment = total
                status = "denied"

                financials = {
                    "expected": total,
                    "received": received,
                    "adjustment": adjustment,
                    "status": status,
                    "reason": "Rejected by payer",
                }

                await self.log_step(
                    "PaymentAgent",
                    "Payment denied from rejected ACK",
                    financials,
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

            # ---------------------------------------------------
            # Step 3: Generate ERA and calculate financials
            # ---------------------------------------------------
            else:
                print("➡️ [2] Generating ERA 835...")

                await self.log_step(
                    "PaymentAgent",
                    "Generating ERA",
                    {
                        "submission_id": submission_id,
                        "expected_amount": total,
                    },
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                financials = test_financials

                scenario = financials["scenario"]
                received = financials["received_amount"]
                paid_amount = financials["paid_amount"]
                adjustment = financials["adjustment"]
                patient_responsibility = financials["patient_responsibility"]
                variance = financials["variance"]
                status = financials["payment_status"]
                era_status = financials["era_status"]
                payment_reason = financials["reason"]

                era = {
                    "type": "835",
                    "claim_id": submission_id,
                    "source_claim_id": claim_id,
                    "status": era_status,
                    "paid_amount": paid_amount,
                    "expected_amount": total,
                    "adjustment_amount": adjustment,
                    "patient_responsibility": patient_responsibility,
                    "variance": variance,
                    "payment_rate_percent": financials["payment_rate_percent"],
                    "reason": payment_reason,
                    "denial_code": financials.get("denial_code"),
                    "scenario": scenario,
                }

                claim["payment"] = era

                print("✅ ERA 835 generated")
                print(f"📦 ERA: {era}")

                if status == "paid":
                    update_record_status(claim_id, "PAID")
                elif status == "underpaid":
                    update_record_status(claim_id, "UNDERPAID")
                elif status == "overpaid":
                    update_record_status(claim_id, "OVERPAID")
                elif status == "paid_with_adjustment":
                    update_record_status(claim_id, "PAID_WITH_ADJUSTMENT")
                elif status == "denied":
                    update_record_status(claim_id, "PAYMENT_DENIED")
                else:
                    update_record_status(claim_id, str(status).upper())

                financials = {
                    **financials,
                    "expected": total,
                    "received": received,
                    "paid_amount": paid_amount,
                    "adjustment": adjustment,
                    "patient_responsibility": patient_responsibility,
                    "variance": variance,
                    "status": status,
                    "reason": payment_reason,
                    "era": era,
                }

                await self.log_step(
                    "PaymentAgent",
                    "Calculating financials",
                    {
                        "era": era,
                        "financials": financials,
                    },
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                

            # ---------------------------------------------------
            # Step 4: Calculate payment metrics
            # ---------------------------------------------------
            print("➡️ [3] Calculating payment metrics...")

            payment_rate = received / total if total else 0
            payment_rate_percent = round(payment_rate * 100)
            duration_seconds = round(time.time() - start_time, 2)
            underpayment_alert = financials.get("underpayment_alert", detect_underpayment(total, received))
            payment_date = (
                claim.get("payment_date")
                or (era.get("payment_date") if isinstance(era, dict) else None)
                or time.strftime("%Y-%m-%d")
            )

            if status == "denied":
                next_agent = "Case Orchestrator"
                result_status = "FAILED"
                pipeline_state = "PAYMENT_DENIED"
                pipeline_status = "DENIED"
            elif status in {"underpaid", "overpaid", "paid_with_adjustment"}:
                next_agent = "Learning Agent"
                result_status = "COMPLETED"
                pipeline_state = "PAYMENT_RECONCILIATION_REQUIRED"
                pipeline_status = status.upper()
            else:
                next_agent = "Learning Agent"
                result_status = "COMPLETED"
                pipeline_state = "PAYMENT_COMPLETED"
                pipeline_status = "PAID"
            payment_message = (
                "Payment completed"
                if status == "paid"
                else f"Payment completed with status: {status}"
            )

            payment_payload = {
                "claim_id": claim_id,
                "agent": "PaymentAgent",
                "submission_id": submission_id,

                # Overall payment event result
                "status": result_status,
                "payment_status": status,
                "payment_scenario": scenario,

                # Amounts / reimbursement reconciliation
                "total_charge": total,
                "billed_amount": total,
                "expected_amount": total,
                "expected_reimbursement": total,
                "paid_amount": financials["paid_amount"],
                "payment_amount": financials["paid_amount"],
                "received_amount": received,
                "adjustment_amount": adjustment,
                "patient_responsibility": financials.get("patient_responsibility", 0.0),
                "payment_variance": financials.get("variance", 0.0),

                # Rates / flags
                "payment_rate": payment_rate,
                "payment_rate_percent": payment_rate_percent,
                "underpayment_alert": financials.get("underpayment_alert", False),
                "overpayment_alert": financials.get("overpayment_alert", False),
                "denial_at_payment": financials.get("denial_at_payment", False),

                # Reason / denial info
                "payment_reason": financials.get("reason"),
                "denial_code": financials.get("denial_code"),

                # Metadata
                "payment_date": payment_date,
                "payer": claim.get("payer"),
                "era": era,
                "financials": financials,
                "trace_id": trace_id,
                "duration_seconds": duration_seconds,

                # Pipeline state
                "current_stage": "PAYMENT",
                "current_agent": "PaymentAgent",
                "active_step": "payment",
                "pipeline_state": pipeline_state,
                "pipeline_status": pipeline_status,
                "progress": 88,
                "current_task": payment_message,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "next_agent": next_agent,
            }           

            claim["payment_result"] = payment_payload
            claim["payment_status"] = status
            claim["payment_scenario"] = scenario
            claim["paid_amount"] = financials["paid_amount"]
            claim["payment_amount"] = financials["paid_amount"]
            claim["received_amount"] = received
            claim["expected_reimbursement"] = total
            claim["adjustment_amount"] = adjustment
            claim["patient_responsibility"] = financials["patient_responsibility"]
            claim["payment_variance"] = financials["variance"]
            claim["underpayment_alert"] = financials.get("underpayment_alert", False)
            claim["overpayment_alert"] = financials.get("overpayment_alert", False)
            claim["denial_at_payment"] = financials.get("denial_at_payment", False)
            claim["payment_duration_seconds"] = duration_seconds
            claim["payment_rate_percent"] = payment_rate_percent

            if status == "denied":
                claim["status"] = "PAYMENT_DENIED"
                claim["stage"] = "PAYMENT"
                claim["denial"] = {
                    "denied": True,
                    "denial_code": financials.get("denial_code", "CO-16"),
                    "denial_reason": financials.get("reason"),
                    "source": "payment_era",
                }
            elif status in {"underpaid", "overpaid", "paid_with_adjustment"}:
                claim["status"] = "PAYMENT_RECONCILIATION_REQUIRED"
                claim["stage"] = "PAYMENT"
            else:
                claim["status"] = "PAID"
                claim["stage"] = "PAYMENT"

            agent_detail_status = (
                "COMPLETED"
                if status == "paid"
                else "WARNING"
            )
            agent_detail = self.build_agent_detail(
                "payment",
                status=agent_detail_status,
                active_step="Payment posting completed",
                message=f"Payment status: {status}",
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=status == "paid",
                score=payment_rate_percent,
                errors=[financials.get("reason")] if financials.get("reason") else [],
                warnings=[underpayment_alert] if underpayment_alert else [],
                output=payment_payload,
                next_agent=next_agent,
            )
            self.apply_agent_detail(
                claim,
                "payment",
                agent_detail,
                step_completed=status == "paid",
                result_status=pipeline_status,
            )
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="PAYMENT",
                status=result_status,
                progress=88,
                current_stage="PAYMENT",
                current_agent="PaymentAgent",
                active_step="payment",
                pipeline_state=pipeline_state,
                pipeline_status=pipeline_status,
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=payment_message,
            )
            claim["pipeline"]["steps"]["payment_processed"] = True
            claim["pipeline"]["steps"]["paid"] = status == "paid"
            claim["pipeline"]["steps"]["underpaid"] = status == "underpaid"
            claim["pipeline"]["steps"]["payment_denied"] = status == "denied"

            print("✅ Payment metrics calculated")
            print(f"💰 Expected: {total}")
            print(f"💵 Received: {received}")
            print(f"📉 Adjustment: {adjustment}")
            print(f"📊 Payment rate: {payment_rate_percent}%")
            print(f"📌 Payment status: {status}")
            print(f"⏱️ Payment duration: {duration_seconds}s")

            # ---------------------------------------------------
            # Step 5: Audit log
            # ---------------------------------------------------
            print("➡️ [4] Writing payment audit log...")

            log_audit(
                claim_id,
                "payment",
                "completed",
                {
                    **financials,
                    "payment_rate_percent": payment_rate_percent,
                    "duration_seconds": duration_seconds,
                    "trace_id": trace_id,
                },
            )

            print("✅ Payment audit log written")

            # ---------------------------------------------------
            # Step 6: Send frontend events
            # ---------------------------------------------------
            print("➡️ [5] Sending payment events to frontend...")

            await send_pipeline_event(
                manager,
                topic="payment",
                action="completed",
                claim_id=claim_id,
                stage="PAYMENT",
                status=result_status,
                progress=88,
                current_stage="PAYMENT",
                current_agent="PaymentAgent",
                active_step="payment",
                pipeline_state=pipeline_state,
                pipeline_status=pipeline_status,
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=payment_message,
                claim=claim,
                extra={
                    "payment": payment_payload,
                    "payment_status": status,
                    "paid_amount": financials["paid_amount"],
                    "payment_result": payment_payload,
                    "financials": financials,
                    "trace_id": trace_id,
                    "agent_detail": agent_detail,
                },
            )

            print("✅ Payment events sent")

            # ---------------------------------------------------
            # Step 7: Metrics
            # ---------------------------------------------------
            print("➡️ [6] Updating payment metrics service...")

            update_metrics(
                event_type="payment_completed",
                claim_id=claim_id,
                agent="PAYMENT",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status=str(status).upper(),
            )

            print("✅ Payment metrics updated")

            # ---------------------------------------------------
            # Step 8: End logs and return
            # ---------------------------------------------------
            await self.log_end(
                "PaymentAgent",
                status,
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            print("✅ [PaymentAgent] COMPLETED")
            print(f"📌 Final payment status: {status}")
            print(f"⏭️ Next agent: {next_agent}")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "financials": financials,
                "payment": payment_payload,
                "pipeline": claim.get("pipeline", {}),
                "stage": status,
                "status": result_status,
                "pipeline_state": pipeline_state,
                "pipeline_status": pipeline_status,
                "current_stage": "PAYMENT",
                "current_agent": "PaymentAgent",
                "active_step": "payment",
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [PaymentAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Payment duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            await self.log_error(
                "PaymentAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            log_audit(
                claim_id,
                "payment",
                "failed",
                {
                    "error": str(error),
                    "duration_seconds": duration_seconds,
                    "trace_id": trace_id,
                },
            )

            failure_payload = {
                "claim_id": claim_id,
                "agent": "PaymentAgent",
                "status": "failed",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "current_stage": "PAYMENT",
                "current_agent": "PaymentAgent",
                "active_step": "payment",
                "pipeline_state": "PAYMENT_FAILED",
                "pipeline_status": "FAILED",
                "progress": 88,
                "review_required": False,
                "approval_required": False,
                "pipeline_paused": False,
                "next_agent": "Case Orchestrator",
            }

            agent_detail = self.build_agent_detail(
                "payment",
                status="FAILED",
                active_step="Payment processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output=failure_payload,
                next_agent="Case Orchestrator",
            )
            self.apply_agent_detail(
                claim,
                "payment",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )
            apply_pipeline_patch(
                claim,
                claim_id=claim_id,
                stage="PAYMENT",
                status="FAILED",
                progress=88,
                current_stage="PAYMENT",
                current_agent="PaymentAgent",
                active_step="payment",
                pipeline_state="PAYMENT_FAILED",
                pipeline_status="FAILED",
                review_required=False,
                approval_required=False,
                pipeline_paused=False,
                message=str(error),
            )
            claim["pipeline"]["steps"]["payment_processed"] = False
            claim["pipeline"]["steps"]["paid"] = False

            await send_pipeline_event(
                manager,
                topic="payment",
                action="failed",
                claim_id=claim_id,
                stage="PAYMENT",
                status="FAILED",
                progress=88,
                current_stage="PAYMENT",
                current_agent="PaymentAgent",
                active_step="payment",
                pipeline_state="PAYMENT_FAILED",
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

            update_metrics(
                event_type="payment_failed",
                claim_id=claim_id,
                agent="PAYMENT",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            await self.log_end(
                "PaymentAgent",
                "FAILED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            return {
                "claim": claim,
                "pipeline": claim.get("pipeline", {}),
                "stage": "payment_failed",
                "status": "FAILED",
                "pipeline_state": "PAYMENT_FAILED",
                "pipeline_status": "FAILED",
                "current_stage": "PAYMENT",
                "current_agent": "PaymentAgent",
                "active_step": "payment",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

    def _safe_float(self, value, default=0.0):
        return _safe_float(value, default)

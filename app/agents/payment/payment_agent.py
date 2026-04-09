# from app.agents.base.base_agent import BaseAgent
# from app.core.state_machine import ClaimStatus
# from app.websocket.manager import manager
# from app.services.reconciliation_service import reconcile_payment
# from app.services.audit_service import log_audit
# from app.services.analytics_service import update_metrics


# class PaymentAgent(BaseAgent):

#     async def run(self, claim):

#         print("💰 [PaymentAgent] Started")
#         await self.log("[PaymentAgent] Processing payment")

#         await manager.send_event("payment", "running")

#     try:
#         claim["status"] = ClaimStatus.PAID.value

#     # -------------------------
#     # 🔥 NORMALIZE SERVICES
#     # -------------------------
#     for s in claim.get("services", []):
#         try:
#             s["units"] = int(s.get("units") or 1)
#         except:
#             s["units"] = 1

#         try:
#             s["charge"] = float(s.get("charge") or 0)
#         except:
#             s["charge"] = 0

#             print("💰 Normalized services:", claim.get("services"))

#             # -------------------------
#             # Step 1: Calculate totals
#             # -------------------------
#             calculated_total = sum(
#             s.get("charge", 0) * s.get("units", 1)
#             for s in claim.get("services", [])
#             )

#             total_charge = claim.get("total_charge")

#             # ✅ THIS MUST ALIGN WITH try
#         except Exception as e:
#             print("❌ PaymentAgent Error:", str(e))
#         raise

#             # -------------------------
#             # Step 1.1: Add warning if mismatch
#             # -------------------------
#             if total_charge and abs(total_charge - calculated_total) > 1:
#                 claim["warnings"] = claim.get("warnings", [])
#                 claim["warnings"].append("Total charge mismatch detected")

#             # -------------------------
#             # Step 1.2: Decide final total
#             # -------------------------
#             if not total_charge or abs(total_charge - calculated_total) > 1:
#                 total_charge = calculated_total

#             # (Optional but useful)
#             claim["calculated_total"] = calculated_total

#             # -------------------------
#             # Step 2: Reconciliation
#             # -------------------------
#             payment_input = {
#                 "paid_amount": 250,
#                 "expected_amount": total_charge
#             }

#             recon = reconcile_payment(claim, payment_input)
#             claim["reconciliation"] = recon

#             received = recon.get("received", 0)

#             # -------------------------
#             # Step 3: Payment status
#             # -------------------------
#             if received < total_charge:
#                 claim["payment_status"] = "partial"
#             elif received > total_charge:
#                 claim["payment_status"] = "overpaid"
#             else:
#                 claim["payment_status"] = "paid"

#             # -------------------------
#             # Step 4: Metrics + Audit
#             # -------------------------
#             update_metrics("payment")

#             log_audit(
#                 claim.get("claim_id"),
#                 "payment",
#                 "completed",
#                 {
#                     "paid_amount": 250,
#                     "expected_amount": total_charge,
#                     "reconciliation": recon,
#                     "payment_status": claim.get("payment_status")
#                 }
#             )

#             # -------------------------
#             # Step 5: WebSocket Event
#             # -------------------------
#             await manager.send_event("payment", "completed", {
#                 "paid_amount": 250,
#                 "expected_amount": total_charge,
#                 "reconciliation": recon,
#                 "payment_status": claim.get("payment_status")
#             })

#             print("✅ Payment completed")

#             # -------------------------
#             # Step 6: Return
#             # -------------------------
#             return {
#                 "claim": claim,
#                 "paid": True,
#                 "payment": {
#                     "paid_amount": 250,
#                     "reconciliation": recon
#                 },
#                 "stage": "paid"
#             }

#         except Exception as e:
#             print("❌ PaymentAgent Error:", str(e))

#             log_audit(
#                 claim.get("claim_id"),
#                 "payment",
#                 "failed",
#                 {"error": str(e)}
#             )

#             await manager.send_event("payment", "failed", {"error": str(e)})

#             raise



# from app.agents.base.base_agent import BaseAgent

# class PaymentAgent(BaseAgent):

#     async def run(self, claim):

#         print("💰 [PaymentAgent] Started")
        
#         # If it wasn't marked paid, simulate partial payment occasionally
#         total = claim.get("total_charge", 0)

#         if claim.get("status") == "paid":
#             received = total
#         else:
#             received = total * 0.95

#         adjustment = total - received

#         status = "paid" if received == total else "underpaid"

#         claim["payment_status"] = status

#         financials = {
#             "expected": total,
#             "received": received,
#             "adjustment": adjustment,
#             "status": status
#         }

#         from app.services.audit_service import log_audit
#         from app.websocket.manager import manager
        
#         log_audit(claim.get("claim_id"), "payment", "completed", financials)
#         await manager.send_event("payment", "completed", financials)

#         return {
#             "claim": claim,
#             "financials": financials,
#             "pipeline": {
#                 "steps": {
#                     "paid": True
#                 }
#             },
#             "stage": "paid"
#         }

from app.agents.base.base_agent import BaseAgent

# 🆕 ADD THESE
from app.rcm.edi_responses import generate_era_835
from app.intake.db_service import update_record_status
from app.rcm.submission import (
    fetch_status,
    record_ack,
    record_denial,
)


class PaymentAgent(BaseAgent):

    async def run(self, claim):

        print("💰 [PaymentAgent] Started")

        total = claim.get("total_charge", 0)
        submission_id = claim.get("submission_id")

        # -------------------------
        # 🔹 1. Check ACK status
        # -------------------------
        ack_status = claim.get("ack", {}).get("ack_277", {}).get("status")

        # -------------------------
        # ❌ DENIED FLOW
        # -------------------------
        if ack_status == "REJECTED":

            record_denial(
                submission_id,
                "D001",
                "Rejected by payer"
            )

            claim["status"] = "denied"
            claim["payment_status"] = "denied"

            financials = {
                "expected": total,
                "received": 0,
                "adjustment": total,
                "status": "denied"
            }

        else:
            # -------------------------
            # 🔥 2. GENERATE ERA FIRST
            # -------------------------
            era = generate_era_835(submission_id, total)

            claim["payment"] = era

            # -------------------------
            # 🔥 3. USE ERA AS SOURCE OF TRUTH
            # -------------------------
            received = era.get("paid_amount", total)

            adjustment = total - received

            if received == 0:
                status = "denied"
            elif adjustment == 0:
                status = "paid"
            else:
                status = "underpaid"

            claim["payment_status"] = status

            # -------------------------
            # 🔹 4. UPDATE DB STATUS
            # -------------------------
            if status == "paid":
                update_record_status(claim["claim_id"], "PAID")

            elif status == "underpaid":
                update_record_status(claim["claim_id"], "UNDERPAID")

            else:
                update_record_status(claim["claim_id"], "DENIED")

            # -------------------------
            # 🔹 5. FINANCIAL SUMMARY
            # -------------------------
            financials = {
                "expected": total,
                "received": received,
                "adjustment": adjustment,
                "status": status
            }

        # -------------------------
        # 🔹 6. AUDIT + EVENTS
        # -------------------------
        from app.services.audit_service import log_audit
        from app.websocket.manager import manager

        log_audit(
            claim.get("claim_id"),
            "payment",
            "completed",
            financials
        )

        await manager.send_event("payment", "completed", financials)

        return {
            "claim": claim,
            "financials": financials,
            "pipeline": {
                "steps": {
                    "paid": True
                }
            },
            "stage": "paid"
        }
# import time

# from app.agents.base.base_agent import BaseAgent
# from app.agents.denial_ai.llm_denial_agent import LLMDenialAgent
# from app.websocket.manager import manager
# from app.services.audit_service import log_audit
# from app.services.analytics_service import update_metrics


# class DenialAgent(BaseAgent):
#     def __init__(self):
#         super().__init__()
#         self.denial_ai = LLMDenialAgent()

#     def classify_denial(self, claim):
#         """AI + Rule-based classification"""
#         denial_code = claim.get("denial_code")

#         mapping = {
#             "CO-50": {
#                 "category": "coding_error",
#                 "reason": "Invalid CPT or missing modifiers",
#                 "confidence": 0.95,
#                 "auto_fixable": True,
#             },
#             "CO-16": {
#                 "category": "missing_info",
#                 "reason": "Missing required information",
#                 "confidence": 0.9,
#                 "auto_fixable": True,
#             },
#             "CO-29": {
#                 "category": "eligibility",
#                 "reason": "Patient not eligible",
#                 "confidence": 0.85,
#                 "auto_fixable": False,
#             },
#         }

#         return mapping.get(
#             denial_code,
#             {
#                 "category": "unknown",
#                 "reason": "Unknown denial reason",
#                 "confidence": 0.5,
#                 "auto_fixable": False,
#             },
#         )

#     def auto_correct(self, claim, classification):
#         """Apply automated fixes"""
#         if classification["category"] == "coding_error":
#             claim["modifiers_fixed"] = True
#             claim["status"] = "corrected"
#             return "Modifier added and CPT corrected"

#         if classification["category"] == "missing_info":
#             claim["missing_fields_filled"] = True
#             claim["status"] = "corrected"
#             return "Missing fields auto-filled"

#         return None

#     async def run(self, claim):
#         start_time = time.time()
#         claim = claim or {}
#         claim_id = claim.get("claim_id", "UNKNOWN")

#         trace_id = await self.log_start("DenialAgent", claim_id)

#         await manager.send_event("denial", "running", {
#             "claim_id": claim_id,
#         })

#         try:
#             # 🔍 Step 1: Classification
#             classification = self.classify_denial(claim)

#             await self.log_step(
#                 "DenialAgent",
#                 "Denial Classification",
#                 classification,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             decision = "auto_fix" if classification["auto_fixable"] and classification["confidence"] > 0.8 else "hitl"

#             await self.log_step(
#                 "DenialAgent",
#                 "Decision Engine",
#                 {"decision": decision},
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             suggestion = None

#             # ⚙️ Step 2: Auto Fix
#             if decision == "auto_fix":
#                 suggestion = self.auto_correct(claim, classification)
#                 claim["resubmission_required"] = True
#                 claim["status"] = "ready_for_resubmission"

#             # 👨‍⚕️ Step 3: HITL
#             else:
#                 claim["status"] = "requires_manual_review"
#                 claim["assigned_to"] = "billing_team"

#             # 📊 Final Risk Object
#             claim["denial_risk"] = {
#                 "risk_score": classification["confidence"],
#                 "category": classification["category"],
#                 "reason": classification["reason"],
#                 "decision": decision,
#                 "suggestion": suggestion,
#             }

#             if decision == "hitl" or claim.get("resubmission_required") or claim.get("status") in {"denied", "requires_manual_review", "ready_for_resubmission"}:
#                 denial_ai_state = await self.denial_ai.run(claim, claim["denial_risk"])
#                 claim = denial_ai_state.get("claim", claim)
#                 if classification["auto_fixable"]:
#                     claim = self.denial_ai.auto_fix(claim, claim.get("denial_ai", {}))
#                     claim["resubmission_required"] = True

#             claim["denial_checked"] = True

#             # 📦 Audit Logging
#             log_audit(
#                 claim_id,
#                 "denial",
#                 "completed",
#                 {
#                     "claim_id": claim_id,
#                     **claim["denial_risk"],
#                     "trace_id": trace_id,
#                 },
#             )

#             await manager.send_event(
#                 "denial",
#                 "completed",
#                 {
#                     **claim["denial_risk"],
#                     "trace_id": trace_id,
#                 },
#             )
#             update_metrics(
#                 event_type="denial_completed",
#                 claim_id=claim_id,
#                 agent="DENIAL",
#                 payer=claim.get("payer"),
#                 risk_score=claim.get("denial_risk", {}).get("risk_score", claim.get("risk_score", 0)),
#                 latency=time.time() - start_time,
#                 status="COMPLETED",
#             )

#             await self.log_end(
#                 "DenialAgent",
#                 "SUCCESS",
#                 time.time() - start_time,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             return {
#                 "claim": claim,
#                 "denial_risk": claim.get("denial_risk"),
#                 "pipeline": {
#                     "steps": {
#                         "denial_checked": True,
#                         "denial_ai_analyzed": bool(claim.get("denial_ai")),
#                         "appeal_generated": bool(claim.get("denial_ai", {}).get("appeal_text")),
#                         "resubmission_required": claim.get("resubmission_required", False),
#                     }
#                 },
#                 "stage": "denial_processed",
#                 "trace_id": trace_id,
#             }

#         except Exception as error:
#             await self.log_error(
#                 "DenialAgent",
#                 error,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             log_audit(
#                 claim_id,
#                 "denial",
#                 "failed",
#                 {"claim_id": claim_id, "error": str(error), "trace_id": trace_id},
#             )

#             await manager.send_event(
#                 "denial",
#                 "failed",
#                 {"error": str(error), "trace_id": trace_id},
#             )
#             update_metrics(
#                 event_type="denial_failed",
#                 claim_id=claim_id,
#                 agent="DENIAL",
#                 payer=claim.get("payer"),
#                 risk_score=claim.get("denial_risk", {}).get("risk_score", claim.get("risk_score", 0)),
#                 latency=time.time() - start_time,
#                 status="FAILED",
#             )

#             await self.log_end(
#                 "DenialAgent",
#                 "FAILED",
#                 time.time() - start_time,
#                 trace_id=trace_id,
#                 claim_id=claim_id,
#             )

#             raise


import time

from app.agents.base.base_agent import BaseAgent
from app.agents.denial_ai.llm_denial_agent import LLMDenialAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit
from app.services.analytics_service import update_metrics


class DenialAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.denial_ai = LLMDenialAgent()

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}
        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "=" * 80)
        print("🚫 [DenialAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        trace_id = await self.log_start("DenialAgent", claim_id)

        await manager.send_event("denial", "running", {
            "claim_id": claim_id,
            "trace_id": trace_id,
            "message": "Denial Agent started",
            "stage": "DENIAL",
            "current_stage": "DENIAL",
            "current_agent": "DenialAgent",
            "active_step": "denial",
            "progress": 80,
            "pipeline_state": "DENIAL_RUNNING",
            "pipeline_status": "RUNNING",
        })

        try:
            print("➡️ [1] Checking whether claim is denied...")

            status = str(claim.get("status") or "").lower()
            ack = claim.get("ack") or claim.get("acknowledgment") or {}
            submission = claim.get("submission") or {}

            raw_response = (
                ack.get("raw_response")
                or ack.get("raw")
                or {}
            )

            denial_code = (
                claim.get("denial_code")
                or ack.get("denial_code")
                or raw_response.get("denial_code")
                or submission.get("denial_code")
            )

            clearinghouse_status = str(
                raw_response.get("status")
                or submission.get("status")
                or ""
            ).upper()

            denial_found = (
                status == "denied"
                or bool(denial_code)
                or clearinghouse_status == "DENIED"
            )

            print(f"📌 Claim status: {status}")
            print(f"📌 Clearinghouse status: {clearinghouse_status}")
            print(f"📌 Denial code: {denial_code}")
            print(f"📌 Denial found: {denial_found}")

            await self.log_step(
                "DenialAgent",
                "Denial presence check",
                {
                    "claim_status": status,
                    "clearinghouse_status": clearinghouse_status,
                    "denial_code": denial_code,
                    "denial_found": denial_found,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # ---------------------------------------------------
            # No denial path
            # ---------------------------------------------------
            if not denial_found:
                print("✅ No denial found")

                duration_seconds = round(time.time() - start_time, 2)

                denial_payload = {
                    "claim_id": claim_id,
                    "agent": "DenialAgent",
                    "status": "completed",
                    "denial_found": False,
                    "denial_code": None,
                    "denial_type": None,
                    "reason": "No denial found for this claim",
                    "risk_score": 0,
                    "risk_score_percent": 0,
                    "suggestions": [],
                    "appeal": None,
                    "duration_seconds": duration_seconds,
                    "next_agent": "Payment Agent",
                    "trace_id": trace_id,
                }

                claim["denial"] = denial_payload
                claim["denial_risk"] = {
                    "risk_score": 0,
                    "reason": "No denial found",
                    "suggestion": None,
                }
                claim["denial_checked"] = True
                claim["denial_found"] = False
                claim["denial_duration_seconds"] = duration_seconds

                agent_detail = self.build_agent_detail(
                    "denial",
                    status="COMPLETED",
                    active_step="Denial check completed",
                    message="No denial found for this claim",
                    started_at=started_at,
                    duration_seconds=duration_seconds,
                    passed=True,
                    risk_score=0,
                    risk_score_percent=0,
                    output=denial_payload,
                    next_agent="Payment Agent",
                )
                self.apply_agent_detail(
                    claim,
                    "denial",
                    agent_detail,
                    step_completed=True,
                    result_status="NO_DENIAL",
                )

                log_audit(
                    claim_id,
                    "denial",
                    "completed",
                    denial_payload,
                )

                await manager.send_event(
                    "denial",
                    "completed",
                    self.build_agent_event_payload(
                        "denial",
                        claim_id,
                        agent_detail,
                        existing_payload=denial_payload,
                        result_status="NO_DENIAL",
                    ),
                )

                update_metrics(
                    event_type="denial_completed",
                    claim_id=claim_id,
                    agent="DENIAL",
                    payer=claim.get("payer"),
                    risk_score=0,
                    latency=duration_seconds,
                    status="NO_DENIAL",
                )

                await self.log_end(
                    "DenialAgent",
                    "NO_DENIAL",
                    duration_seconds,
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                print(f"⏱️ Denial duration: {duration_seconds}s")
                print("⏭️ Next agent: Payment Agent")
                print("=" * 80 + "\n")

                return {
                    "claim": claim,
                    "denial_risk": claim.get("denial_risk"),
                    "denial": denial_payload,
                    "pipeline": {
                        "steps": {
                            "denial_checked": True,
                            "denial_ai_analyzed": False,
                            "appeal_generated": False,
                            "resubmission_required": False,
                        }
                    },
                    "stage": "denial_checked",
                    "status": "NO_DENIAL",
                    "duration_seconds": duration_seconds,
                    "trace_id": trace_id,
                    "agent_detail": agent_detail,
                }

            # ---------------------------------------------------
            # Denial found path
            # ---------------------------------------------------
            print("⛔ Denial found. Running denial AI analysis...")

            denial_context = {
                "denial_code": denial_code,
                "reason": claim.get("denial_reason") or raw_response.get("reason"),
                "status": "denied",
            }

            denial_ai_state = await self.denial_ai.run(claim, denial_context)

            claim = denial_ai_state.get("claim", claim)
            denial_ai = denial_ai_state.get("denial_ai") or claim.get("denial_ai") or {}
            appeal = denial_ai_state.get("appeal") or {}

            retry_probability = denial_ai.get("retry_probability", 0.45)

            try:
                risk_score = float(retry_probability)
            except (TypeError, ValueError):
                risk_score = 0.45

            risk_score_percent = round(risk_score * 100)

            duration_seconds = round(time.time() - start_time, 2)

            denial_payload = {
                "claim_id": claim_id,
                "agent": "DenialAgent",
                "status": "denied",
                "denial_found": True,
                "denial_code": denial_code or denial_ai.get("denial_code"),
                "denial_type": denial_ai.get("category"),
                "root_cause": denial_ai.get("root_cause"),
                "reason": denial_ai.get("denial_reason") or denial_ai.get("root_cause"),
                "risk_score": risk_score,
                "risk_score_percent": risk_score_percent,
                "suggested_corrections": denial_ai.get("suggested_corrections", []),
                "modifier_suggestions": denial_ai.get("modifier_suggestions", []),
                "icd_suggestions": denial_ai.get("icd_suggestions", []),
                "documentation_gaps": denial_ai.get("documentation_gaps", []),
                "denial_prevention_tips": denial_ai.get("denial_prevention_tips", []),
                "resubmission_strategy": denial_ai.get("resubmission_strategy"),
                "appeal": appeal,
                "appeal_text": denial_ai.get("appeal_text"),
                "duration_seconds": duration_seconds,
                "next_agent": "Case Orchestrator",
                "trace_id": trace_id,
            }

            claim["denial"] = denial_payload
            claim["denial_risk"] = {
                "risk_score": risk_score,
                "category": denial_payload["denial_type"],
                "reason": denial_payload["reason"],
                "suggestion": denial_payload["resubmission_strategy"],
            }
            claim["denial_checked"] = True
            claim["denial_found"] = True
            claim["denial_duration_seconds"] = duration_seconds
            claim["status"] = "denied"
            claim["resubmission_required"] = True

            agent_detail = self.build_agent_detail(
                "denial",
                status="WARNING",
                active_step="Denial analysis completed",
                message=denial_payload.get("reason") or "Denial detected",
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                risk_score=risk_score,
                risk_score_percent=risk_score_percent,
                errors=[denial_payload.get("reason")] if denial_payload.get("reason") else [],
                warnings=denial_payload.get("denial_prevention_tips", []),
                output=denial_payload,
                next_agent="Case Orchestrator",
            )
            self.apply_agent_detail(
                claim,
                "denial",
                agent_detail,
                step_completed=True,
                result_status="DENIED",
            )

            log_audit(
                claim_id,
                "denial",
                "denied",
                denial_payload,
            )

            await manager.send_event(
                "denial",
                "denied",
                self.build_agent_event_payload(
                    "denial",
                    claim_id,
                    agent_detail,
                    existing_payload=denial_payload,
                    result_status="DENIED",
                ),
            )

            update_metrics(
                event_type="denial_detected",
                claim_id=claim_id,
                agent="DENIAL",
                payer=claim.get("payer"),
                risk_score=risk_score,
                latency=duration_seconds,
                status="DENIED",
            )

            await self.log_end(
                "DenialAgent",
                "DENIED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            print("⛔ Denial analysis completed")
            print(f"📌 Denial code: {denial_payload['denial_code']}")
            print(f"📌 Denial type: {denial_payload['denial_type']}")
            print(f"📌 Reason: {denial_payload['reason']}")
            print(f"📊 Risk score: {risk_score_percent}%")
            print(f"⏱️ Denial duration: {duration_seconds}s")
            print("⏭️ Next agent: Case Orchestrator")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "denial_risk": claim.get("denial_risk"),
                "denial": denial_payload,
                "pipeline": {
                    "steps": {
                        "denial_checked": True,
                        "denial_ai_analyzed": True,
                        "appeal_generated": bool(denial_payload.get("appeal_text")),
                        "resubmission_required": True,
                    }
                },
                "stage": "denied",
                "status": "DENIED",
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [DenialAgent] FAILED")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Denial duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            await self.log_error(
                "DenialAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            log_audit(
                claim_id,
                "denial",
                "failed",
                {
                    "claim_id": claim_id,
                    "error": str(error),
                    "duration_seconds": duration_seconds,
                    "trace_id": trace_id,
                },
            )

            failure_payload = {
                "claim_id": claim_id,
                "error": str(error),
                "duration_seconds": duration_seconds,
                "next_agent": "Case Orchestrator",
                "trace_id": trace_id,
            }
            agent_detail = self.build_agent_detail(
                "denial",
                status="FAILED",
                active_step="Denial processing failed",
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
                "denial",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )

            await manager.send_event(
                "denial",
                "failed",
                self.build_agent_event_payload(
                    "denial",
                    claim_id,
                    agent_detail,
                    existing_payload=failure_payload,
                    result_status="FAILED",
                    failed=True,
                    error=error,
                    duration_seconds=duration_seconds,
                ),
            )

            update_metrics(
                event_type="denial_failed",
                claim_id=claim_id,
                agent="DENIAL",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            await self.log_end(
                "DenialAgent",
                "FAILED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            return {
                "claim": claim,
                "pipeline": {
                    "steps": {
                        "denial_checked": False
                    }
                },
                "stage": "denial_failed",
                "status": "FAILED",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "trace_id": trace_id,
                "agent_detail": agent_detail,
            }

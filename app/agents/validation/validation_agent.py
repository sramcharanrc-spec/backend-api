# from app.agents.base.base_agent import BaseAgent
# from app.core.state_machine import ClaimStatus
# from app.agents.validation.validation_rules import run_basic_rules
# from app.services.analytics_service import update_metrics
# from app.services.audit_service import log_audit
# from app.websocket.manager import manager


# class ValidationAgent(BaseAgent):

#     async def run(self, claim):

#         print("⚙️ [ValidationAgent] Started")
#         await self.log("Running validation")

#         await manager.send_event("validation", "running")

#         try:
#             # -------------------------
#             # Step 1: Run base rules
#             # -------------------------
#             errors = run_basic_rules(claim)

#             # -------------------------
#             # Step 1.5: Additional validation
#             # -------------------------
#             if claim.get("patient", {}).get("dob") in ["Unknown", None]:
#                 errors.append("Invalid DOB")

#             if claim.get("provider", {}).get("npi") in ["?", None]:
#                 errors.append("Missing NPI")

#             # 🔥 IMPORTANT CHANGE (NON-BLOCKING ICD)
#             if not claim.get("icd_codes"):
#                 claim["warnings"] = claim.get("warnings", [])
#                 claim["warnings"].append("Missing ICD codes (will auto-suggest)")

#             for s in claim.get("services", []):
#                 if not s.get("charge"):
#                     errors.append(f"Missing charge for CPT {s.get('cpt')}")

#             # -------------------------
#             # Step 1.6: Normalize data
#             # -------------------------
#             for s in claim.get("services", []):
#                 s["units"] = s.get("units", 1)
#                 s["charge"] = s.get("charge") or 0

#             # -------------------------
#             # Step 2: Determine status
#             # -------------------------
#             status = "failed" if errors else "passed"

#             # -------------------------
#             # Step 3: Metrics
#             # -------------------------
#             if status == "failed":
#                 update_metrics("validation_failed")
#             else:
#                 update_metrics("validation_passed")

#             # -------------------------
#             # Step 4: Handle failure
#             # -------------------------
#             if errors:
#                 claim["status"] = "needs_review"
#                 claim["validation_errors"] = errors

#                 log_audit(
#                     claim.get("claim_id"),
#                     "validation",
#                     "failed",
#                     {"errors": errors}
#                 )

#                 await manager.send_event(
#                     "validation",
#                     "failed",
#                     {"errors": errors}
#                 )

#                 print("⚠️ Validation failed → HITL")

#                 return {
#                     "claim": claim,
#                     "validation": {
#                         "status": "failed",
#                         "errors": errors
#                     },
#                     "next": "human_review"
#                 }

#             # -------------------------
#             # Step 5: Success
#             # -------------------------
#             claim["status"] = ClaimStatus.VALIDATED.value
#             claim.pop("validation_errors", None)

#             log_audit(
#                 claim.get("claim_id"),
#                 "validation",
#                 "passed",
#                 {"errors": []}
#             )

#             await manager.send_event(
#                 "validation",
#                 "passed",
#                 {"errors": []}
#             )

#             print("✅ Validation passed → Continue pipeline")

#             return {
#                 "claim": claim,
#                 "validation": {
#                     "status": "passed",
#                     "errors": []
#                 }
#             }

#         except Exception as e:
#             print("❌ ValidationAgent Error:", str(e))

#             log_audit(
#                 claim.get("claim_id"),
#                 "validation",
#                 "failed",
#                 {"error": str(e)}
#             )

#             await manager.send_event(
#                 "validation",
#                 "failed",
#                 {"error": str(e)}
#             )

#             raise

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit
from app.orchestrator.case_orchestrator import build_case_record
from app.intake.db_service import update_case

class ValidationAgent(BaseAgent):

    async def run(self, claim):

        print("⚙️ [ValidationAgent] Started")
        await manager.send_event("validation", "running")

        try:
            errors = []

            # -------------------------
            # 🔍 VALIDATION RULES
            # -------------------------
            if not claim.get("patient", {}).get("name"):
                errors.append("Missing patient name")

            if not claim.get("patient", {}).get("dob"):
                errors.append("Missing patient DOB")

            if not claim.get("provider", {}).get("npi"):
                errors.append("Provider NPI missing")

            if not claim.get("services"):
                errors.append("No services found")

            # -------------------------
            # 🧹 CLEAN + NORMALIZE
            # -------------------------
            seen = set()
            unique = []

            for s in claim.get("services", []):
                key = (s.get("cpt"), s.get("units", 1))
                if key not in seen:
                    seen.add(key)
                    unique.append(s)

            claim["services"] = unique

            for s in claim.get("services", []):
                s["units"] = int(s.get("units") or 1)
                s["charge"] = float(s.get("charge") or 0)

            total = sum(s["charge"] * s["units"] for s in claim["services"])
            claim["total_charge"] = total

            # -------------------------
            # 🚨 HITL CONDITION
            # -------------------------
            if errors:
                print("⛔ Validation failed → HITL")

                # 🔥 CREATE CASE HERE (FIX)
                case = build_case_record(claim)
                update_case(claim.get("claim_id"), case)

                log_audit(
                    claim.get("claim_id"),
                    "validation",
                    "failed",
                    {"errors": errors}
                )

                await manager.send_event(
                    "validation",
                    "failed",
                    {"errors": errors}
                )

                return {
                    "claim": claim,
                    "case": case,   # ✅ FIXED
                    "status": "HITL_REQUIRED",

                    "validation": {
                        "valid": False,
                        "status": "failed",
                        "errors": errors
                    },

                    "pipeline": {
                        "steps": {
                            "rules_validated": False,
                            "case_orchestrated": True   # 🔥 IMPORTANT
                        }
                    },

                    "stage": "HUMAN_REVIEW"
                }

            # -------------------------
            # ✅ SUCCESS
            # -------------------------
            print("✅ Validation passed")

            log_audit(
                claim.get("claim_id"),
                "validation",
                "passed",
                {}
            )

            await manager.send_event("validation", "completed", {})

            return {
                "claim": claim,

                "status": "SUCCESS",

                "validation": {
                    "valid": True,
                    "status": "passed",
                    "errors": []
                },

                "pipeline": {
                    "steps": {
                        "rules_validated": True
                    }
                },

                "stage": "VALIDATED"
            }

        except Exception as e:
            log_audit(
                claim.get("claim_id"),
                "validation",
                "failed",
                {"error": str(e)}
            )
            raise
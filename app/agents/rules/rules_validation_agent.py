# from app.agents.base.base_agent import BaseAgent 
# from app.agents.validation.rule_engine import validate_claim
# from app.agents.rules.medicare_rules import medicare_rules
# from app.services.audit_service import log_audit
# from app.services.auto_correction_service import auto_fix_claim
# from app.websocket.manager import manager
# from app.agents.bedrock.client import BedrockClient
# import json


# class RulesValidationAgent(BaseAgent):

#     def __init__(self):
#         super().__init__()
#         self.llm = BedrockClient()

#     async def run(self, claim):

#         print("⚙️ [RulesValidationAgent] Started")

#         # ✅ FIX 1: INSIDE function
#         await manager.broadcast({
#             "event": "pipeline_update",
#             "stage": "rules_validation",
#             "status": "running"
#         })

#         # -------------------------
#         # Step 1: Rule Engine
#         # -------------------------
#         results = validate_claim(claim, medicare_rules)
#         errors = []

#         # -------------------------
#         # Step 2: AI Suggestions
#         # -------------------------
#         for r in results:
#             if not r.get("passed"):

#                 try:
#                     suggestion = await self.llm.invoke(
#                         f"""
# You are a healthcare revenue cycle (RCM) expert.

# Claim Context:
# {json.dumps(claim, indent=2)}

# Validation Error:
# Field: {r.get('field')}
# Issue: {r.get('message')}

# Return ONLY corrected value.
# """
#                     )

#                 except Exception as e:
#                     print("❌ AI Error:", str(e))
#                     suggestion = "99213"

#                 errors.append({
#                     "field": r.get("field"),
#                     "message": r.get("message"),
#                     "suggestion": suggestion.strip()
#                 })

#         # -------------------------
#         # Step 3: Auto Fix
#         # -------------------------
#         if errors:
#             print("🧠 Auto-correcting claim...")

#             claim = auto_fix_claim(claim, errors)

#             print("🔁 Re-validating...")

#             results = validate_claim(claim, medicare_rules)

#             errors = [
#                 {
#                     "field": r.get("field"),
#                     "message": r.get("message"),
#                     "suggestion": "Auto-fix failed"
#                 }
#                 for r in results if not r.get("passed")
#             ]

#         # -------------------------
#         # Step 4: Normalize DOB
#         # -------------------------
#         if isinstance(claim.get("patient"), dict):
#             if claim.get("patient_dob"):
#                 claim["patient"]["dob"] = claim.get("patient_dob")

#         # -------------------------
#         # Step 5: Status
#         # -------------------------
#         status = "failed" if errors else "completed"

#         print(f"⚙️ Final Status: {status}")

#         # -------------------------
#         # Step 6: Remove duplicate CPTs
#         # -------------------------
#         services = claim.get("services", [])
#         seen = set()
#         unique_services = []

#         for s in services:
#             cpt = s.get("cpt")
#             units = s.get("units", 1)

#             if not cpt:
#                 continue

#             key = (cpt, units)

#             if key not in seen:
#                 seen.add(key)
#                 unique_services.append(s)

#         claim["services"] = unique_services

#         # -------------------------
#         # Step 7: Audit
#         # -------------------------
#         log_audit(
#             claim.get("claim_id"),
#             "rules_validation",
#             status,
#             {"errors": errors}
#         )

#         # -------------------------
#         # Step 8: WebSocket
#         # -------------------------
#         await manager.send_event(
#             "rules_validation",
#             status,
#             {"errors": errors}
#         )

#         # -------------------------
#         # Step 9: Return
#         # -------------------------
#         return {
#             "claim": claim,

#             # 🔥 ADD THIS
#             "pipeline": {
#                 "steps": {
#                     "rules_validated": status == "completed"
#                 }
#             },

#             "validation": {
#             "status": status,
#             "errors": errors
#             },

#             "stage": "validated" if status == "completed" else "validation_failed"
#         }

from app.agents.base.base_agent import BaseAgent
from app.services.audit_service import log_audit
from app.websocket.manager import manager


# class RulesValidationAgent(BaseAgent):

#     async def run(self, claim):

#         print("⚙️ [RulesValidationAgent] Started (SIMPLE MODE)")

#         await manager.send_event("rules_validation", "running")

#         errors = []

#         # -------------------------
#         # Simple validation only
#         # -------------------------
#         if not claim.get("patient"):
#             errors.append("Missing patient")

#         if not claim.get("provider"):
#             errors.append("Missing provider")

#         if not claim.get("services"):
#             errors.append("No services found")

#         # -------------------------
#         # Decide status
#         # -------------------------
#         status = "completed"  # 🔥 ALWAYS COMPLETE (NO BLOCKING)

#         # -------------------------
#         # Audit
#         # -------------------------
#         log_audit(
#             claim.get("claim_id"),
#             "rules_validation",
#             status,
#             {"errors": errors}
#         )

#         # -------------------------
#         # WebSocket
#         # -------------------------
#         await manager.send_event(
#             "rules_validation",
#             status,
#             {"errors": errors}
#         )

#         print("✅ Rules validation done (no blocking)")

#         # -------------------------
#         # Return
#         # -------------------------
#         return {
#             "claim": claim,

#             "pipeline": {
#                 "steps": {
#                     "rules_validated": True   # 🔥 FORCE TRUE
#                 }
#             },

#             "validation": {
#                 "status": status,
#                 "errors": errors
#             },

#             "stage": "validated"
#         }

class RulesValidationAgent(BaseAgent):

    async def run(self, claim):

        print("⚙️ [RulesValidationAgent] Started")

        await manager.send_event("rules_validation", "running")

        errors = []

        # -------------------------
        # VALIDATION RULES
        # -------------------------
        if not claim.get("patient"):
            errors.append("Missing patient")

        if not claim.get("provider"):
            errors.append("Missing provider")

        if not claim.get("services"):
            errors.append("No services found")

        # 🔥 ADD IMPORTANT FIELD CHECKS
        if not claim.get("provider", {}).get("npi"):
            errors.append("Provider NPI missing")

        if not claim.get("patient", {}).get("dob"):
            errors.append("Patient DOB missing")

        # -------------------------
        # DECIDE STATUS
        # -------------------------
        is_valid = len(errors) == 0

        status = "completed" if is_valid else "failed"

        # -------------------------
        # AUDIT
        # -------------------------
        log_audit(
            claim.get("claim_id"),
            "rules_validation",
            status,
            {"errors": errors}
        )

        # -------------------------
        # WEBSOCKET
        # -------------------------
        await manager.send_event(
            "rules_validation",
            status,
            {"errors": errors}
        )

        # -------------------------
        # 🚨 HITL BLOCK
        # -------------------------
        if not is_valid:
            print("⛔ Validation failed → HITL triggered")

            return {
                "claim": claim,

                "status": "HITL_REQUIRED",
                "stage": "human_review",

                "pipeline": {
                    "steps": {
                        "rules_validated": False,
                        "submitted": False,
                        "paid": False,
                        "analytics_done": False
                    }
                },

                "validation": {
                    "valid": False,
                    "status": "failed",
                    "errors": errors
                }
            }

        # -------------------------
        # ✅ SUCCESS PATH
        # -------------------------
        print("✅ Rules validation passed")

        return {
            "claim": claim,

            "pipeline": {
                "steps": {
                    "rules_validated": True
                }
            },

            "validation": {
                "valid": True,
                "status": "completed",
                "errors": []
            },

            "stage": "validated"
        }
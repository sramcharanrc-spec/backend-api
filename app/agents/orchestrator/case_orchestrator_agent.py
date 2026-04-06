# import uuid
# from app.agents.base.base_agent import BaseAgent


# class CaseOrchestratorAgent(BaseAgent):

#     async def run(self, claim):

#         print("[CaseOrchestrator] Creating case")

#         # -------------------------
#         # Step 1: Ensure claim_id
#         # -------------------------
#         if "claim_id" not in claim:
#             claim["claim_id"] = f"CLM-{uuid.uuid4().hex[:10]}"

#         # -------------------------
#         # Step 2: Initialize case
#         # -------------------------
#         claim["case_status"] = "OPEN"
#         claim["assigned_team"] = "Claims Processing"
#         claim["sla_hours"] = 24

#         print("🆔 Claim ID:", claim["claim_id"])

#         # -------------------------
#         # Step 3: Return (NO validation here ❌)
#         # -------------------------
#         return {
#             "claim": claim,

#             "case": {
#                 "case_id": claim["claim_id"],
#                 "status": "OPEN",
#                 "assigned_to": "MA"
#             },

#             "pipeline": {
#                 "steps": {
#                     "case_orchestrated": True
#                 }
#             },

#             "case_orchestrated": True,
#             "stage": "case_created"
#         }

from app.agents.base.base_agent import BaseAgent
from app.orchestrator.case_orchestrator import build_case_record


class CaseOrchestratorAgent(BaseAgent):

    async def run(self, state):

        print("📁 [CaseOrchestrator] Evaluating case creation")

        claim = state.get("claim", {})
        validation = state.get("validation", {})
        denial = claim.get("denial_risk", {})

        # -------------------------
        # 🔥 STOP if HITL already triggered
        # -------------------------
        if state.get("status") == "HITL_REQUIRED":
            print("⛔ Skipping case → HITL already active")

            return {
                "claim": claim,
                "case": None,
                "pipeline": {
                    "steps": {
                        "case_orchestrated": False
                    }
                },
                "stage": "case_skipped"
            }

        # -------------------------
        # 🔍 CONDITIONS
        # -------------------------
        errors = validation.get("errors", [])
        risk_score = denial.get("risk_score", 0)
        missing_dob = not claim.get("patient", {}).get("dob")

        should_create_case = False

        if errors:
            should_create_case = True
        elif risk_score > 0.7:
            should_create_case = True
        elif missing_dob:
            should_create_case = True

        # -------------------------
        # ❌ NO CASE
        # -------------------------
        if not should_create_case:
            print("✅ No case needed")

            return {
                "claim": claim,
                "case": None,
                "pipeline": {
                    "steps": {
                        "case_orchestrated": True
                    }
                },
                "stage": "case_skipped"
            }

        # -------------------------
        # ✅ CREATE CASE
        # -------------------------
        print("⚠️ Creating case...")

        case = build_case_record(claim, denial)

        print(f"📁 Case Created: {case['case_id']}")

        return {
            "claim": claim,
            "case": case,
            "pipeline": {
                "steps": {
                    "case_orchestrated": True
                }
            },
            "stage": "case_created"
        }
from app.orchestrator.case_orchestrator import build_case_record


class CaseOrchestratorAgent:

    async def run(self, claim):

        print("[CaseOrchestrator] Evaluating case creation")

        # -------------------------
        # Get data
        # -------------------------
        denial = claim.get("denial_risk", {})
        risk_score = denial.get("risk_score", 0)

        validation_errors = claim.get("validation_errors", [])
        missing_dob = not claim.get("patient", {}).get("dob")

        # -------------------------
        # 🔥 CONDITION LOGIC
        # -------------------------
        should_create_case = False

        if validation_errors:
            should_create_case = True
        elif risk_score > 0.7:
            should_create_case = True
        elif missing_dob:
            should_create_case = True

        # -------------------------
        # ❌ NO CASE → CLEAR
        # -------------------------
        if not should_create_case:
            print("✅ No case needed → skipping")

            return {
                "claim": claim,
                "case": None,  # ✅ clean output
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
            "case": case,  # ✅ clean
            "pipeline": {
                "steps": {
                    "case_orchestrated": True
                }
            },
            "stage": "case_created"
        }
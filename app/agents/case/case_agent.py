import time

from app.agents.base.base_agent import BaseAgent
from app.orchestrator.case_orchestrator import build_case_record


class CaseOrchestratorAgent(BaseAgent):

    async def run(self, claim):
        start_time = time.time()
        claim = claim or {}
        claim_id = claim.get("claim_id", "UNKNOWN")
        trace_id = await self.log_start("CaseOrchestratorAgent", claim_id)

        try:
            denial = claim.get("denial_risk", {})
            risk_score = denial.get("risk_score", 0)
            validation_errors = claim.get("validation_errors", [])
            missing_dob = not claim.get("patient", {}).get("dob")

            await self.log_step(
                "CaseOrchestratorAgent",
                "Evaluating case creation criteria",
                {
                    "risk_score": risk_score,
                    "validation_errors": validation_errors,
                    "missing_dob": missing_dob,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            should_create_case = False
            if validation_errors:
                should_create_case = True
            elif risk_score > 0.7:
                should_create_case = True
            elif missing_dob:
                should_create_case = True

            if not should_create_case:
                await self.log_step(
                    "CaseOrchestratorAgent",
                    "Case skipped",
                    {"reason": "No qualifying validation or denial risk criteria"},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )
                await self.log_end(
                    "CaseOrchestratorAgent",
                    "SKIPPED",
                    time.time() - start_time,
                    trace_id=trace_id,
                    claim_id=claim_id,
                )
                return {
                    "claim": claim,
                    "case": None,
                    "pipeline": {"steps": {"case_orchestrated": True}},
                    "stage": "case_skipped",
                    "trace_id": trace_id,
                }

            case = build_case_record(claim, denial)
            await self.log_step(
                "CaseOrchestratorAgent",
                "Case created",
                case,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            await self.log_end(
                "CaseOrchestratorAgent",
                "CREATED",
                time.time() - start_time,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            return {
                "claim": claim,
                "case": case,
                "pipeline": {"steps": {"case_orchestrated": True}},
                "stage": "case_created",
                "trace_id": trace_id,
            }

        except Exception as error:
            await self.log_error(
                "CaseOrchestratorAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            await self.log_end(
                "CaseOrchestratorAgent",
                "FAILED",
                time.time() - start_time,
                trace_id=trace_id,
                claim_id=claim_id,
            )
            raise

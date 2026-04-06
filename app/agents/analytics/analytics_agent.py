# from app.agents.base.base_agent import BaseAgent
# from app.services.analytics_service import update_metrics


# class AnalyticsAgent(BaseAgent):

#     async def run(self, claim):

#         print("📊 [AnalyticsAgent] Started")

#         denial = claim.get("denial_risk", {})
#         risk_score = denial.get("risk_score", 0.0)

#         claim["analytics"] = {
#             "risk_score": risk_score,
#             "processed": True
#         }

#         update_metrics("processed_claim")

#         print("📊 Analytics completed")

#         return {
#             "claim": claim,

#             "pipeline": {
#                 "steps": {
#                     "analytics_done": True
#                 }
#             },

#             "stage": "analytics_done"
#         }

from app.agents.base.base_agent import BaseAgent

class AnalyticsAgent(BaseAgent):

    async def run(self, claim):

        print("📊 [AnalyticsAgent] Started")

        denial = claim.get("denial_risk") or {}

        claim["analytics"] = {
            "risk_score": float(denial.get("risk_score") or 0),
            "total_charge": claim.get("total_charge"),
            "service_count": len(claim.get("services", [])),
            "processed": True
        }

        return {
            "claim": claim,
            "pipeline": {
                "steps": {
                    "analytics_done": True
                }
            },
            "stage": "analytics_done"
        }
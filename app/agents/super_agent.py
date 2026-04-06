from app.agents.bedrock.client import BedrockClient
import random


class SuperAgent:

    async def decide(self, state):

        steps = state.get("pipeline", {}).get("steps", {})

        print("🧠 SUPERVISOR STEPS:", steps)

        # 🔥 ALWAYS READ FROM PIPELINE.STEPS

        if not steps.get("case_orchestrated"):
            return {"next": "case_orchestrator"}

        elif not steps.get("eligibility_checked"):
            return {"next": "eligibility"}

        elif not steps.get("rules_validated"):
            return {"next": "rules_validation"}

        elif not steps.get("submitted"):
            return {"next": "submission"}

        elif not steps.get("denial_checked"):
            return {"next": "denial"}

        elif not steps.get("paid"):
            return {"next": "payment"}

        elif not steps.get("analytics_done"):
            return {"next": "analytics"}

        else:
            return {"next": "finish"}
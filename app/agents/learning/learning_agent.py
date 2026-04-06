from app.agents.base.base_agent import BaseAgent


class LearningAgent(BaseAgent):

    async def run(self, claim):

        training_example = {
            "claim_id": claim["claim_id"],
            "risk_score": claim["analytics"]["risk_score"]
        }

        print("Training data stored:", training_example)

        return {
            "claim": claim,
            "learning_logged": True
        }
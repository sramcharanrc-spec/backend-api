# ehr_pipeline/app/agents/acknowledgment/acknowledgment_agent.py

from app.agents.base.base_agent import BaseAgent
from app.core.state_machine import ClaimStatus


class AcknowledgmentAgent(BaseAgent):

    async def run(self, claim):

        await self.log("Checking acknowledgment")

        # Simulated response
        claim.status = ClaimStatus.DENIED.value
        claim.denial_code = "CO-50"

        return claim
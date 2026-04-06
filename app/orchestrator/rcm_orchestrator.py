# ehr_pipeline/app/orchestrator/rcm_orchestrator.py

from app.core.state_machine import ClaimStatus
from app.agents.validation.validation_agent import ValidationAgent
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.acknowledgment.acknowledgment_agent import AcknowledgmentAgent
from app.agents.denial.denial_agent import DenialAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.agents.analytics.analytics_agent import AnalyticsAgent


class RCMOrchestrator:

    def __init__(self):
        self.validation = ValidationAgent()
        self.submission = SubmissionAgent()
        self.ack = AcknowledgmentAgent()
        self.denial = DenialAgent()
        self.payment = PaymentAgent()
        self.analytics = AnalyticsAgent()

    async def process(self, claim):

        claim = await self.validation.run(claim)

        if claim.status == ClaimStatus.FAILED:
            return claim

        claim = await self.submission.run(claim)
        claim = await self.ack.run(claim)

        if claim.status == ClaimStatus.DENIED:
            claim = await self.denial.run(claim)
            claim = await self.submission.run(claim)
            claim = await self.ack.run(claim)

        if claim.status == ClaimStatus.PAID:
            claim = await self.payment.run(claim)

        await self.analytics.run(claim)

        return claim
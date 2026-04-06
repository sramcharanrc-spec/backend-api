from app.agents.base import BaseAgent
from ehr_pipeline.app.lambdas.analytics_agent.analytics import analytics_dashboard

class AnalyticsAgent(BaseAgent):
    name = "Analytics Agent"

    def run(self, payload: dict):
        return analytics_dashboard()

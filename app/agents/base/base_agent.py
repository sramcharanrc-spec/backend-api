# ehr_pipeline/app/agents/base/base_agent.py

from app.agents.base.agent_interface import AgentInterface


class BaseAgent(AgentInterface):

    async def log(self, message: str):
        print(f"[{self.__class__.__name__}] {message}")
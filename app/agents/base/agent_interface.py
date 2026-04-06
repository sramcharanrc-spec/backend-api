# ehr_pipeline/app/agents/base/agent_interface.py

from abc import ABC, abstractmethod


class AgentInterface(ABC):

    @abstractmethod
    async def run(self, claim):
        pass
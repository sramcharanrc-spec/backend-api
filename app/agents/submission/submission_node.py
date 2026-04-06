from app.agents.submission.submission_agent import SubmissionAgent

agent = SubmissionAgent()


async def submission_node(state):
    return await agent.run(state)
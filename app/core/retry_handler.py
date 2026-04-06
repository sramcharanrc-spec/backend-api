from app.core.constants import MAX_RETRY_ATTEMPTS
from app.core.state_machine import ClaimStatus


async def execute_with_retry(agent, claim):

    try:
        return await agent.run(claim)

    except Exception as e:

        claim.retry_count += 1
        claim.last_error = str(e)

        if claim.retry_count >= MAX_RETRY_ATTEMPTS:
            claim.status = ClaimStatus.FAILED
            return claim

        raise e
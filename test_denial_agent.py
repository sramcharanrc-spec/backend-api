import asyncio
import json

from app.agents.denial.denial_agent import DenialAgent
from app.rcm.claim_store import get_claim


async def main():
    claim_id = "CLM-58acbe2296"

    claim = get_claim(claim_id)

    if not claim:
        raise RuntimeError(f"Claim not found: {claim_id}")

    result = await DenialAgent().run({
        "claim": claim,
        "pipeline": claim.get("pipeline", {})
    })

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
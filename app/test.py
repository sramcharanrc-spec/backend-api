import asyncio
from app.agents.validation.validation_agent import ValidationAgent

agent = ValidationAgent()

test_claim = {
    "claim_id": "TEST-001",
    "patient": {"name": "John", "dob": "1990-01-01"},
    "provider": {"npi": "1234567890"},
    "services": [{"cpt": "99214", "charge": 100, "units": 1}],
    "cpt_codes": ["99214"],
    "icd_codes": ["Z00.00"]
}

result = asyncio.run(agent.run(test_claim))

print(result)
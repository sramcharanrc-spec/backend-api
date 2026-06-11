# prompts.py

def denial_prompt(claim):
    return f"""
You are a healthcare RCM expert.

Predict denial risk.

Claim:
CPT: {[s['cpt'] for s in claim.get('services', [])]}
Charge: {claim.get('total_charge')}

Return JSON:
{{
  "risk_score": 0-1,
  "reason": "...",
  "suggestion": "..."
}}
"""


def enrichment_prompt(data):
    return f"""
Strict healthcare assistant.

Fill missing fields only if confident.

Data:
{data}

Return JSON only.
"""
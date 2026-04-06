def denial_prompt(claim: dict) -> str:

    return f"""
You are a healthcare RCM expert.

Analyze this claim and predict denial risk.

Claim:
- CPT Codes: {[s['cpt'] for s in claim.get('services', [])]}
- Total Charge: {claim.get('total_charge')}
- Payer: {claim.get('payer', {}).get('name')}

Return JSON:
{{
  "risk_score": 0-1,
  "reason": "...",
  "suggestion": "..."
}}
"""
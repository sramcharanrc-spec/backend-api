from app.agents.bedrock.client import BedrockClient
import json
import re

llm = BedrockClient()


async def generate_suggestions(extracted_data):

    prompt = f"""
You are a healthcare claims assistant.

Your task is to COMPLETE missing claim fields using the extracted data.

GUIDELINES:
- If a value is clearly present → extract it
- If a value is missing → make a reasonable assumption
- If unsure → return null (do NOT guess randomly)
- Keep responses realistic for US healthcare claims

Return ONLY JSON.

Fields:
- patient_dob (format: YYYY-MM-DD)
- procedure_code (CPT format like 99213)
- provider_npi (10-digit number)
- total_amount (number)
- icd_codes (list of ICD-10 codes)

Extracted Data:
{extracted_data}

Return JSON:
{{
  "patient_dob": "... or null",
  "procedure_code": "... or null",
  "provider_npi": "... or null",
  "total_amount": 0,
  "icd_codes": []
}}
"""

    llm_output = await llm.invoke(prompt)

    # -------------------------
    # ✅ ROBUST PARSING (IMPROVED)
    # -------------------------
    try:
        parsed = json.loads(llm_output)

    except:
        match = re.search(r'\{.*\}', llm_output, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except:
                parsed = {}
        else:
            parsed = {}

    # -------------------------
    # ✅ SAFE FALLBACKS (VERY IMPORTANT)
    # -------------------------
    return {
        "patient_dob": parsed.get("patient_dob"),
        "procedure_code": parsed.get("procedure_code"),
        "provider_npi": parsed.get("provider_npi"),
        "total_amount": parsed.get("total_amount") or 0,
        "icd_codes": parsed.get("icd_codes") or []
    }
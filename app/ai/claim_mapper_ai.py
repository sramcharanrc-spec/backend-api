import json
from app.agents.bedrock.client import BedrockClient

llm = BedrockClient()


def split_sections(text):
    sections = {
        "patient": "",
        "provider": "",
        "insurance": ""
    }

    current = None
    for line in text.split("\n"):
        if "Patient" in line:
            current = "patient"
        elif "Provider" in line:
            current = "provider"

        if current:
            sections[current] += line + "\n"

    return sections


async def map_claim_with_ai(extracted):

    prompt = f"""
You are a healthcare RCM expert.

The OCR data contains multiple sections:
- Patient Information
- Provider
- Insurance
- Services

STRICT RULES:

1. Patient Section:
   - Extract ONLY patient name from "Patient Information"
   - NEVER leave patient.name empty if any name exists
   - DO NOT use provider name as patient name

2. Provider Section:
   - Extract provider name ONLY from provider section

3. Services:
   - Extract ALL CPT codes (DO NOT miss any)
   - CPT must be 5 digits
   - Charges must be numbers

4. NEVER overwrite patient.name with provider.name

-----------------------------------
OCR DATA:
{json.dumps(extracted, indent=2)}
-----------------------------------

Return ONLY JSON:

{{
  "patient": {{
    "name": "...",
    "dob": "YYYY-MM-DD"
  }},
  "provider": {{
    "name": "...",
    "npi": "..."
  }},
  "payer": {{
    "name": "..."
  }},
  "services": [
    {{
      "cpt": "...",
      "charge": number
    }}
  ],
  "total_charge": number
}}

NO explanation. ONLY JSON.
"""

    response = await llm.invoke(prompt)

    try:
        parsed = json.loads(response)

        # -------------------------
        # 🚨 STRONG SAFETY FIX
        # -------------------------
        patient_name = parsed.get("patient", {}).get("name")
        provider_name = parsed.get("provider", {}).get("name")

        if not patient_name or patient_name == provider_name:

            parsed["warnings"] = parsed.get("warnings", [])
            parsed["warnings"].append("Patient name missing or incorrect → auto-corrected")

            # 🔥 MULTI-FALLBACK
            fallback_name = (
                extracted.get("patient_name") or
                extracted.get("Name") or
                extracted.get("Patient Name") or
                "Unknown"
            )

            parsed.setdefault("patient", {})
            parsed["patient"]["name"] = fallback_name

        return parsed

    except Exception as e:
        print("❌ AI parsing failed:", str(e))
        return {
            "error": "AI parsing failed",
            "raw": response
        }
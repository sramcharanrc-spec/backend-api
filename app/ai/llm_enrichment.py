import re
from datetime import datetime
from app.ai.llm_service import invoke_llm


# -------------------------
# VALIDATORS
# -------------------------
def is_valid_npi(npi):
    return isinstance(npi, str) and re.fullmatch(r"\d{10}", npi)


def is_valid_cpt(code):
    return isinstance(code, str) and re.fullmatch(r"\d{5}", code)


def is_valid_icd(code):
    return isinstance(code, str) and re.fullmatch(r"[A-Z][0-9A-Z.]{2,6}", code)


def is_valid_date(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except:
        return False


# -------------------------
# 🔥 1. FIELD ENRICHMENT
# -------------------------
async def enrich_claim_fields(extracted):

    prompt = f"""
Strict healthcare assistant.

Fill only if confident. Otherwise return null.

Data:
{extracted}

Return JSON:
{{
  "patient_dob": null,
  "procedure_code": null,
  "provider_npi": null,
  "total_amount": 0,
  "icd_codes": []
}}
"""

    parsed = await invoke_llm(prompt)

    # validation
    return {
        "patient_dob": parsed.get("patient_dob") if is_valid_date(parsed.get("patient_dob")) else None,
        "procedure_code": parsed.get("procedure_code") if is_valid_cpt(parsed.get("procedure_code")) else None,
        "provider_npi": parsed.get("provider_npi") if is_valid_npi(parsed.get("provider_npi")) else None,
        "total_amount": parsed.get("total_amount") or 0,
        "icd_codes": [c for c in parsed.get("icd_codes", []) if is_valid_icd(c)]
    }


# -------------------------
# 🔥 2. CLAIM MAPPING
# -------------------------
async def map_claim(extracted):

    prompt = f"""
Map OCR data into structured claim JSON.

Data:
{extracted}

Return JSON:
{{
  "patient": {{"name": "", "dob": ""}},
  "provider": {{"name": "", "npi": ""}},
  "services": [],
  "total_charge": 0
}}
"""

    parsed = await invoke_llm(prompt)

    # 🔥 safety fix
    if parsed.get("patient", {}).get("name") == parsed.get("provider", {}).get("name"):
        parsed["patient"]["name"] = extracted.get("patient_name", "Unknown")

    return parsed
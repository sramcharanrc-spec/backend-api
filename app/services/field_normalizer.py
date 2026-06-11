import json
from app.ai.llm_service import invoke_llm
from app.intake.form_normalizer import normalize_fields


def _set_path(data, path, value):
    cursor = data
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _apply_field_map(data):
    if not isinstance(data, dict):
        return data

    mapped = normalize_fields(data)
    if not mapped:
        return data

    normalized = dict(data)
    for path, value in mapped.items():
        _set_path(normalized, path, value)
    return normalized

class FieldNormalizer:

    async def normalize(self, data):
        mapped_data = _apply_field_map(data)

        prompt = f"""
Clean and standardize this healthcare claim.

Fix:
- field names
- CPT / ICD codes
- date formats

Return JSON.

Input:
{json.dumps(mapped_data)}
"""

        response = await invoke_llm(prompt)

        if isinstance(response, dict) and response.get("error"):
            return mapped_data

        return _apply_field_map(response)

from __future__ import annotations

from typing import Any


def map_s3_json_to_claim(raw_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_data, dict):
        raw_data = {"raw": raw_data}

    return {
        "claim_id": raw_data.get("claim_id") or raw_data.get("id") or "AUTO-GEN-CLAIM",
        "patient": raw_data.get("patient") or {
            "name": raw_data.get("patient_name", "Unknown"),
            "dob": raw_data.get("patient_dob", raw_data.get("dob", "")),
        },
        "provider": raw_data.get("provider") or {
            "name": raw_data.get("provider_name", ""),
            "npi": raw_data.get("provider_npi", raw_data.get("npi", "")),
        },
        "services": raw_data.get("services", []),
        "total_charge": raw_data.get("total_charge", raw_data.get("total_amount", 0)),
        "raw": raw_data,
    }


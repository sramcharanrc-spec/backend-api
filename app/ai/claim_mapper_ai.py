from __future__ import annotations

from typing import Any

from app.ai.llm_enrichment import map_claim


def _first_present(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_service_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    services = data.get("services")
    if isinstance(services, list) and services:
        normalized = []
        for service in services:
            if not isinstance(service, dict):
                continue
            cpt = _first_present(service, "cpt", "procedure_code", "procedure_codes", default="99214")
            normalized.append(
                {
                    "cpt": str(cpt),
                    "charge": _safe_float(_first_present(service, "charge", "amount", "total", default=100), 100),
                    "units": int(_safe_float(service.get("units"), 1) or 1),
                }
            )
        if normalized:
            return normalized

    codes = _first_present(data, "cpt_codes", "procedure_codes", "procedure_code", default="99214")
    if isinstance(codes, str):
        codes = [code.strip() for code in codes.split(",") if code.strip()]
    if not isinstance(codes, list) or not codes:
        codes = ["99214"]

    charge = _safe_float(_first_present(data, "total_charge", "total_amount", "charge", default=100), 100)
    per_line_charge = charge / len(codes) if codes else charge
    return [{"cpt": str(code), "charge": per_line_charge, "units": 1} for code in codes]


def _fallback_claim(extracted: dict[str, Any]) -> dict[str, Any]:
    services = _safe_service_list(extracted)
    total_charge = _safe_float(
        _first_present(extracted, "total_charge", "total_amount", "charge", default=0),
        0,
    )
    if total_charge <= 0:
        total_charge = sum(
            _safe_float(service.get("charge")) * _safe_float(service.get("units"), 1)
            for service in services
        )

    return {
        "patient": {
            "name": _first_present(extracted, "patient_name", "name", default="Unknown"),
            "dob": _first_present(extracted, "patient_dob", "dob", "date_of_birth", default="1990-01-01"),
        },
        "provider": {
            "name": _first_present(extracted, "provider_name", default=""),
            "npi": str(_first_present(extracted, "provider_npi", "npi", default="0000000000")),
        },
        "payer": {
            "name": _first_present(extracted, "payer_name", "insurance", default=""),
        },
        "services": services,
        "cpt_codes": [service["cpt"] for service in services if service.get("cpt")],
        "total_charge": total_charge,
    }


def _ensure_claim_schema(claim: Any, extracted: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(claim, dict) or claim.get("error"):
        return _fallback_claim(extracted)

    fallback = _fallback_claim(extracted)
    claim.setdefault("patient", fallback["patient"])
    claim.setdefault("provider", fallback["provider"])
    claim.setdefault("payer", fallback["payer"])
    claim.setdefault("services", fallback["services"])
    claim.setdefault("total_charge", fallback["total_charge"])

    if not isinstance(claim["patient"], dict):
        claim["patient"] = fallback["patient"]
    if not isinstance(claim["provider"], dict):
        claim["provider"] = fallback["provider"]
    if not isinstance(claim["services"], list) or not claim["services"]:
        claim["services"] = fallback["services"]

    claim["patient"].setdefault("name", fallback["patient"]["name"])
    claim["patient"].setdefault("dob", fallback["patient"]["dob"])
    claim["provider"].setdefault("npi", fallback["provider"]["npi"])
    claim["total_charge"] = _safe_float(claim.get("total_charge"), fallback["total_charge"])
    claim["cpt_codes"] = [service.get("cpt") for service in claim["services"] if isinstance(service, dict) and service.get("cpt")]

    return claim


async def map_claim_with_ai(extracted: dict[str, Any]) -> dict[str, Any]:
    """Map extracted intake data into the claim schema expected by the RCM pipeline."""
    if not isinstance(extracted, dict):
        extracted = {"raw_text": str(extracted)}

    try:
        ai_claim = await map_claim(extracted)
    except Exception:
        ai_claim = None

    return _ensure_claim_schema(ai_claim, extracted)

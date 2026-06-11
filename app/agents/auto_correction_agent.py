from copy import deepcopy
from typing import Any, Dict, List

from app.agents.ai_suggestions.auto_correct_agent import validate_npi


class AutoCorrectionAgent:
    """DEV-stage claim repair agent using transparent demo rules."""

    def correct(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        corrected = deepcopy(claim)
        changes: List[Dict[str, Any]] = []

        provider = corrected.setdefault("provider", {})
        if not provider.get("npi") or provider.get("npi") in {"?", "UNKNOWN", "Unknown"}:
            changes.append(self._change("provider.npi", provider.get("npi"), None, "Provider NPI missing; routed to human review"))
            corrected["requires_hitl"] = True
            corrected["pipeline_state"] = "WAITING_FOR_REVIEW"
            corrected["pipeline_status"] = "WAITING_FOR_REVIEW"
            corrected["status"] = "WAITING_FOR_REVIEW"
            corrected["current_stage"] = "WAITING_FOR_REVIEW"
            corrected["active_step"] = "waiting_for_review"
            corrected["current_agent"] = "SUBMISSION_REVIEW"
        elif not validate_npi(provider.get("npi")):
            changes.append(self._change("provider.npi", provider.get("npi"), None, "Invalid provider NPI; routed to human review"))
            provider.pop("npi", None)
            corrected["requires_hitl"] = True
            corrected["pipeline_state"] = "WAITING_FOR_REVIEW"
            corrected["pipeline_status"] = "WAITING_FOR_REVIEW"
            corrected["status"] = "WAITING_FOR_REVIEW"
            corrected["current_stage"] = "WAITING_FOR_REVIEW"
            corrected["active_step"] = "waiting_for_review"
            corrected["current_agent"] = "SUBMISSION_REVIEW"

        for index, service in enumerate(corrected.get("services") or []):
            cpt = str(service.get("cpt") or service.get("code") or "").strip()
            if cpt == "9921B":
                changes.append(self._change(f"services[{index}].cpt", cpt, "99213", "Normalized OCR CPT confusion"))
                service["cpt"] = "99213"
            if str(service.get("cpt")) == "99213" and "25" not in service.get("modifiers", []):
                original = list(service.get("modifiers", []))
                service["modifiers"] = original + ["25"]
                changes.append(self._change(f"services[{index}].modifiers", original, service["modifiers"], "Suggested modifier for separately identifiable E/M review"))
            if not service.get("units"):
                changes.append(self._change(f"services[{index}].units", service.get("units"), 1, "Defaulted missing units"))
                service["units"] = 1

        payer = corrected.setdefault("payer", {})
        if payer.get("name") and not payer.get("payer_id"):
            payer_id = str(payer["name"]).upper().replace(" ", "-")[:24]
            changes.append(self._change("payer.payer_id", None, payer_id, "Generated demo payer routing id"))
            payer["payer_id"] = payer_id

        corrected["corrected_fields"] = changes
        return {"claim": corrected, "corrected_fields": changes, "correction_count": len(changes)}

    @staticmethod
    def _change(field: str, original: Any, corrected: Any, reason: str) -> Dict[str, Any]:
        return {
            "field": field,
            "original_value": original,
            "corrected_value": corrected,
            "correction_reason": reason,
        }


def auto_correct_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    return AutoCorrectionAgent().correct(claim)

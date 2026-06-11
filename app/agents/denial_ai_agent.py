from typing import Any, Dict, List


class DenialAIAgent:
    """DEV-stage denial intelligence with deterministic demo heuristics."""

    def analyze(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        services: List[Dict[str, Any]] = claim.get("services") or []
        diagnosis = claim.get("icd_codes") or claim.get("diagnosis_codes") or []
        payer = claim.get("payer") or {}
        issues = []
        risk = 18

        cpts = {str(item.get("cpt") or item.get("code") or "") for item in services}
        modifiers = {str(mod) for item in services for mod in item.get("modifiers", [])}

        if "99213" in cpts and "25" not in modifiers:
            issues.append("Modifier 25 missing for CPT 99213")
            risk += 32
        if not diagnosis:
            issues.append("Missing ICD diagnosis linkage")
            risk += 28
        if not claim.get("provider", {}).get("npi"):
            issues.append("Provider NPI missing")
            risk += 20
        if str(payer.get("name", "")).upper() in {"MEDICARE", "CMS"} and "G2211" in cpts:
            issues.append("Payer-specific review recommended for G2211 add-on code")
            risk += 12

        risk = min(risk, 98)
        reason = issues[0] if issues else "No obvious denial trigger detected"
        confidence = 0.91 if issues else 0.72

        return {
            "denial_prediction": "LIKELY" if risk >= 60 else "UNLIKELY",
            "denial_reason": reason,
            "denial_explanation": "; ".join(issues) if issues else "Claim passes demo denial heuristics.",
            "ai_suggestion": self._suggestion(reason),
            "auto_correction_hints": issues,
            "risk_score": risk,
            "confidence": confidence,
        }

    def _suggestion(self, reason: str) -> str:
        if "Modifier 25" in reason:
            return "Review E/M documentation and add modifier 25 to CPT 99213 when a separately identifiable service is supported."
        if "ICD" in reason:
            return "Map each service line to a supported ICD-10 diagnosis before resubmission."
        if "NPI" in reason:
            return "Repair provider NPI from enrollment data or route to MA Team for verification."
        return "Proceed with normal validation and monitor payer response."


def analyze_denial(claim: Dict[str, Any]) -> Dict[str, Any]:
    return DenialAIAgent().analyze(claim)


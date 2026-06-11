# from typing import Any, Dict


# DENIAL_TAXONOMY = {
#     "CO-16": {
#         "category": "missing_information",
#         "root_cause": "Required claim, documentation, or demographic information is missing",
#         "focus": ["patient demographics", "provider identifiers", "service line completeness", "attachments"],
#         "retry_probability": 0.72,
#     },
#     "CO-50": {
#         "category": "medical_necessity",
#         "root_cause": "Service was not supported as medically necessary by diagnosis or documentation",
#         "focus": ["ICD specificity", "medical necessity", "LCD/NCD policy", "documentation gaps"],
#         "retry_probability": 0.64,
#     },
#     "CO-97": {
#         "category": "bundling_or_modifier",
#         "root_cause": "Procedure was bundled, included in another service, or missing required modifier",
#         "focus": ["modifier issues", "CPT pairings", "NCCI edits"],
#         "retry_probability": 0.69,
#     },
#     "CO-29": {
#         "category": "timely_filing",
#         "root_cause": "Claim was submitted outside payer filing limits",
#         "focus": ["timely filing proof", "original submission evidence"],
#         "retry_probability": 0.38,
#     },
# }


# class DenialClassifier:
#     def classify(self, claim: Dict[str, Any], denial: Dict[str, Any] | None = None) -> Dict[str, Any]:
#         denial = denial or {}
#         code = denial.get("denial_code") or claim.get("denial_code") or claim.get("denial", {}).get("denial_code")
#         reason = denial.get("reason") or denial.get("message") or claim.get("denial_reason") or claim.get("denial_risk", {}).get("reason")
#         base = DENIAL_TAXONOMY.get(str(code or "").upper(), {
#             "category": "unknown",
#             "root_cause": reason or "Payer denial requires manual review",
#             "focus": ["payer rules", "documentation", "coding"],
#             "retry_probability": 0.45,
#         })
#         return {
#             "denial_code": code or "UNKNOWN",
#             "denial_reason": reason or base["root_cause"],
#             **base,
#         }

import time
from typing import Any, Dict, List



DENIAL_TAXONOMY = {
    "CO-16": {
        "category": "missing_information",
        "root_cause": "Required claim, documentation, or demographic information is missing",
        "focus": [
            "patient demographics",
            "provider identifiers",
            "service line completeness",
            "attachments",
        ],
        "retry_probability": 0.72,
        "severity": "HIGH",
    },
    "CO-50": {
        "category": "medical_necessity",
        "root_cause": "Service was not supported as medically necessary by diagnosis or documentation",
        "focus": [
            "ICD specificity",
            "medical necessity",
            "LCD/NCD policy",
            "documentation gaps",
        ],
        "retry_probability": 0.64,
        "severity": "HIGH",
    },
    "CO-97": {
        "category": "bundling_or_modifier",
        "root_cause": "Procedure was bundled, included in another service, or missing required modifier",
        "focus": [
            "modifier issues",
            "CPT pairings",
            "NCCI edits",
        ],
        "retry_probability": 0.69,
        "severity": "HIGH",
    },
    "CO-29": {
        "category": "timely_filing",
        "root_cause": "Claim was submitted outside payer filing limits",
        "focus": [
            "timely filing proof",
            "original submission evidence",
        ],
        "retry_probability": 0.38,
        "severity": "HIGH",
    },
    "CO-197": {
        "category": "authorization_missing",
        "root_cause": "Prior authorization, precertification, or referral is missing",
        "focus": [
            "authorization number",
            "referral",
            "payer approval",
            "precertification",
        ],
        "retry_probability": 0.70,
        "severity": "HIGH",
    },
    "CO-96": {
        "category": "non_covered_service",
        "root_cause": "Service is not covered by the payer or patient plan",
        "focus": [
            "benefit coverage",
            "payer policy",
            "plan exclusions",
        ],
        "retry_probability": 0.42,
        "severity": "MEDIUM",
    },
    "CO-18": {
        "category": "duplicate_claim",
        "root_cause": "Duplicate claim or service was submitted",
        "focus": [
            "duplicate submission",
            "claim history",
            "corrected claim frequency code",
        ],
        "retry_probability": 0.35,
        "severity": "MEDIUM",
    },
    "CO-22": {
        "category": "coordination_of_benefits",
        "root_cause": "Claim may require coordination with another payer",
        "focus": [
            "primary payer",
            "secondary payer",
            "COB information",
        ],
        "retry_probability": 0.58,
        "severity": "MEDIUM",
    },
    "CO-109": {
        "category": "coverage_issue",
        "root_cause": "Claim or service is not covered by this payer or contractor",
        "focus": [
            "payer routing",
            "eligibility",
            "coverage verification",
        ],
        "retry_probability": 0.40,
        "severity": "MEDIUM",
    },
    "CO-4": {
        "category": "modifier_missing_or_invalid",
        "root_cause": "Procedure code is inconsistent with the modifier used or required modifier is missing",
        "focus": [
            "modifier validation",
            "CPT modifier pairing",
            "payer modifier rules",
        ],
        "retry_probability": 0.68,
        "severity": "HIGH",
    },
    "CO-11": {
        "category": "diagnosis_inconsistent",
        "root_cause": "Diagnosis is inconsistent with the procedure billed",
        "focus": [
            "ICD-to-CPT compatibility",
            "documentation support",
            "medical necessity",
        ],
        "retry_probability": 0.62,
        "severity": "HIGH",
    },
}


class DenialClassifier:
    def classify(
        self,
        claim: Dict[str, Any],
        denial: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        start_time = time.time()


        claim = claim or {}
        denial = denial or {}

        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "-" * 80)
        print("🏷️ [DenialClassifier] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📌 Incoming denial data: {denial}")

        code = self._extract_denial_code(claim, denial)
        reason = self._extract_reason(claim, denial)

        print(f"📌 Extracted denial code: {code}")
        print(f"📌 Extracted reason: {reason}")

        base = DENIAL_TAXONOMY.get(code, {
            "category": "unknown",
            "root_cause": reason or "Payer denial requires manual review",
            "focus": [
                "payer rules",
                "documentation",
                "coding",
                "claim history",
            ],
            "retry_probability": 0.45,
            "severity": "MEDIUM",
        })

        retry_probability = self._safe_probability(
            denial.get("retry_probability"),
            base.get("retry_probability", 0.45),
        )

        duration_seconds = round(time.time() - start_time, 2)

        classification = {
            "denial_code": code or "UNKNOWN",
            "denial_reason": reason or base["root_cause"],
            "category": base["category"],
            "root_cause": base["root_cause"],
            "focus": base["focus"],
            "retry_probability": retry_probability,
            "retry_probability_percent": round(retry_probability * 100),
            "severity": base.get("severity", "MEDIUM"),
            "source": "taxonomy" if code in DENIAL_TAXONOMY else "fallback",
            "requires_appeal": self._requires_appeal(base["category"]),
            "can_resubmit": retry_probability >= 0.50,
            "duration_seconds": duration_seconds,
        }

        print("✅ [DenialClassifier] COMPLETED")
        print(f"📂 Category: {classification.get('category')}")
        print(f"📌 Root cause: {classification.get('root_cause')}")
        print(f"📊 Retry probability: {classification.get('retry_probability_percent')}%")
        print(f"⏱️ Classifier duration: {duration_seconds}s")
        print("-" * 80 + "\n")

        return classification

    def _extract_denial_code(
        self,
        claim: Dict[str, Any],
        denial: Dict[str, Any]
    ) -> str:
        raw_code = (
            denial.get("denial_code")
            or denial.get("carc")
            or denial.get("code")
            or claim.get("denial_code")
            or claim.get("carc")
            or claim.get("denial", {}).get("denial_code")
            or claim.get("ack", {}).get("denial_code")
            or claim.get("acknowledgment", {}).get("denial_code")
        )

        code = str(raw_code or "").upper().strip()

        if code and not code.startswith("CO-") and code.replace("-", "").isdigit():
            code = f"CO-{code.replace('-', '')}"

        return code

    def _extract_reason(
        self,
        claim: Dict[str, Any],
        denial: Dict[str, Any]
    ) -> str | None:
        return (
            denial.get("reason")
            or denial.get("message")
            or denial.get("denial_reason")
            or claim.get("denial_reason")
            or claim.get("denial", {}).get("reason")
            or claim.get("denial_risk", {}).get("reason")
        )

    def _safe_probability(self, value, default: float) -> float:
        try:
            probability = float(value if value is not None else default)
        except (TypeError, ValueError):
            probability = default

        if probability > 1:
            probability = probability / 100

        return max(0.0, min(1.0, probability))

    def _requires_appeal(self, category: str) -> bool:
        return category in {
            "medical_necessity",
            "timely_filing",
            "non_covered_service",
            "coverage_issue",
            "authorization_missing",
        }
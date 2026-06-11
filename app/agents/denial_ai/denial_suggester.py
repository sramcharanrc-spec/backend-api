# from typing import Any, Dict, List


# class DenialSuggester:
#     def suggest(self, claim: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
#         category = classification.get("category")
#         suggestions: Dict[str, List[Dict[str, Any]]] = {
#             "suggested_corrections": [],
#             "modifier_suggestions": [],
#             "icd_suggestions": [],
#             "prevention_tips": [],
#         }

#         if category == "missing_information":
#             if not claim.get("provider", {}).get("npi"):
#                 suggestions["suggested_corrections"].append({
#                     "field": "provider.npi",
#                     "suggested": "Verify billing/rendering NPI from provider master",
#                     "confidence": 0.86,
#                 })
#             if not claim.get("patient", {}).get("dob"):
#                 suggestions["suggested_corrections"].append({
#                     "field": "patient.dob",
#                     "suggested": "Populate patient DOB from EHR demographics",
#                     "confidence": 0.84,
#                 })
#             suggestions["prevention_tips"].append("Block submission until required payer fields and attachments are present")

#         if category == "medical_necessity":
#             suggestions["icd_suggestions"].append({
#                 "field": "icd_codes",
#                 "suggested": "Use the most specific diagnosis supported by the note and payer LCD/NCD",
#                 "confidence": 0.74,
#             })
#             suggestions["prevention_tips"].append("Run diagnosis-to-CPT medical necessity policy matching before EDI generation")

#         if category == "bundling_or_modifier":
#             suggestions["modifier_suggestions"].append({
#                 "field": "services.modifier",
#                 "suggested": "Review modifier 25, 59, XE, XP, XS, XU where supported by documentation",
#                 "confidence": 0.76,
#             })
#             suggestions["suggested_corrections"].append({
#                 "field": "services",
#                 "suggested": "Validate CPT pairings against NCCI edits",
#                 "confidence": 0.78,
#             })
#             suggestions["prevention_tips"].append("Run NCCI and payer bundling edits before claim submission")

#         if not any(suggestions.values()):
#             suggestions["prevention_tips"].append("Route payer-specific denial reason to billing specialist for review")

#         return suggestions

import time
from typing import Any, Dict, List
from unicodedata import category
from unicodedata import category


class DenialSuggester:
    def suggest(
        self,
        claim: Dict[str, Any],
        classification: Dict[str, Any]
    ) -> Dict[str, Any]:
        start_time = time.time()
        claim = claim or {}
        classification = classification or {}


        claim_id = claim.get("claim_id", "UNKNOWN")
        category = classification.get("category")

        print("\n" + "-" * 80)
        print("💡 [DenialSuggester] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📂 Denial category: {category}")

        suggestions: Dict[str, Any] = {
            "suggested_corrections": [],
            "modifier_suggestions": [],
            "icd_suggestions": [],
            "documentation_gaps": [],
            "prevention_tips": [],
        }

        if category == "missing_information":
            self._missing_information_suggestions(claim, suggestions)

        elif category == "medical_necessity":
            self._medical_necessity_suggestions(claim, suggestions)

        elif category == "bundling_or_modifier":
            self._bundling_modifier_suggestions(claim, suggestions)

        elif category == "modifier_missing_or_invalid":
            self._modifier_missing_suggestions(claim, suggestions)

        elif category == "authorization_missing":
            self._authorization_suggestions(claim, suggestions)

        elif category == "timely_filing":
            self._timely_filing_suggestions(claim, suggestions)

        elif category == "duplicate_claim":
            self._duplicate_claim_suggestions(claim, suggestions)

        elif category == "coordination_of_benefits":
            self._cob_suggestions(claim, suggestions)

        elif category in {"non_covered_service", "coverage_issue"}:
            self._coverage_suggestions(claim, suggestions)

        elif category == "diagnosis_inconsistent":
            self._diagnosis_inconsistent_suggestions(claim, suggestions)

        else:
            self._unknown_denial_suggestions(classification, suggestions)

        if not any(suggestions.values()):
            suggestions["prevention_tips"].append({
                "tip": "Route payer-specific denial reason to billing specialist for review",
                "priority": "MEDIUM",
            })
        duration_seconds = round(time.time() - start_time, 2)

        
        counts = {
            "suggested_corrections": len(suggestions["suggested_corrections"]),
            "modifier_suggestions": len(suggestions["modifier_suggestions"]),
            "icd_suggestions": len(suggestions["icd_suggestions"]),
            "documentation_gaps": len(suggestions["documentation_gaps"]),
            "prevention_tips": len(suggestions["prevention_tips"]),
        }

        suggestions["duration_seconds"] = duration_seconds
        suggestions["counts"] = counts

        print("✅ [DenialSuggester] COMPLETED")
        print(f"📊 Suggestion counts: {counts}")
        print(f"⏱️ Suggester duration: {duration_seconds}s")
        print("-" * 80 + "\n")
      
        return suggestions

    def _missing_information_suggestions(self, claim, suggestions):
        patient = claim.get("patient") or {}
        provider = claim.get("provider") or {}

        if not provider.get("npi"):
            suggestions["suggested_corrections"].append({
                "field": "provider.npi",
                "suggested": "Verify billing/rendering NPI from provider master",
                "confidence": 0.86,
                "priority": "HIGH",
            })

        if not patient.get("dob"):
            suggestions["suggested_corrections"].append({
                "field": "patient.dob",
                "suggested": "Populate patient DOB from EHR demographics",
                "confidence": 0.84,
                "priority": "HIGH",
            })

        if not claim.get("attachments"):
            suggestions["documentation_gaps"].append({
                "field": "attachments",
                "suggested": "Attach missing supporting documentation requested by payer",
                "confidence": 0.76,
                "priority": "MEDIUM",
            })

        suggestions["prevention_tips"].append({
            "tip": "Block submission until required payer fields and attachments are present",
            "priority": "HIGH",
        })

    def _medical_necessity_suggestions(self, claim, suggestions):
        suggestions["icd_suggestions"].append({
            "field": "icd_codes",
            "suggested": "Use the most specific diagnosis supported by the clinical note and payer policy",
            "confidence": 0.74,
            "priority": "HIGH",
        })

        suggestions["documentation_gaps"].append({
            "field": "medical_records",
            "suggested": "Attach notes proving medical necessity for billed CPT codes",
            "confidence": 0.78,
            "priority": "HIGH",
        })

        suggestions["documentation_gaps"].append({
            "field": "payer_policy",
            "suggested": "Review LCD/NCD or payer medical necessity policy",
            "confidence": 0.72,
            "priority": "MEDIUM",
        })

        suggestions["prevention_tips"].append({
            "tip": "Run diagnosis-to-CPT medical necessity policy matching before EDI generation",
            "priority": "HIGH",
        })

    def _bundling_modifier_suggestions(self, claim, suggestions):
        suggestions["modifier_suggestions"].append({
            "field": "services.modifier",
            "suggested": "Review modifier 25, 59, XE, XP, XS, XU where supported by documentation",
            "confidence": 0.76,
            "priority": "HIGH",
        })

        suggestions["suggested_corrections"].append({
            "field": "services",
            "suggested": "Validate CPT pairings against NCCI and payer bundling edits",
            "confidence": 0.78,
            "priority": "HIGH",
        })

        suggestions["prevention_tips"].append({
            "tip": "Run NCCI and payer bundling edits before claim submission",
            "priority": "HIGH",
        })

    def _modifier_missing_suggestions(self, claim, suggestions):
        suggestions["modifier_suggestions"].append({
            "field": "services.modifier",
            "suggested": "Add or correct required modifier if supported by documentation",
            "confidence": 0.80,
            "priority": "HIGH",
        })

        suggestions["prevention_tips"].append({
            "tip": "Validate payer modifier requirements before submission",
            "priority": "HIGH",
        })

    def _authorization_suggestions(self, claim, suggestions):
        suggestions["suggested_corrections"].append({
            "field": "prior_authorization",
            "suggested": "Attach or enter valid prior authorization, precertification, or referral number",
            "confidence": 0.82,
            "priority": "HIGH",
        })

        suggestions["documentation_gaps"].append({
            "field": "authorization_document",
            "suggested": "Attach payer authorization approval documentation",
            "confidence": 0.80,
            "priority": "HIGH",
        })

        suggestions["prevention_tips"].append({
            "tip": "Check authorization requirements before claim submission",
            "priority": "HIGH",
        })

    def _timely_filing_suggestions(self, claim, suggestions):
        suggestions["documentation_gaps"].append({
            "field": "timely_filing_proof",
            "suggested": "Attach proof of timely filing or original clearinghouse acceptance report",
            "confidence": 0.74,
            "priority": "HIGH",
        })

        suggestions["suggested_corrections"].append({
            "field": "submission_history",
            "suggested": "Verify original submission date and payer filing limit",
            "confidence": 0.70,
            "priority": "MEDIUM",
        })

        suggestions["prevention_tips"].append({
            "tip": "Track payer filing deadlines and submission timestamps",
            "priority": "HIGH",
        })

    def _duplicate_claim_suggestions(self, claim, suggestions):
        suggestions["suggested_corrections"].append({
            "field": "claim_frequency_code",
            "suggested": "Verify whether claim should be voided, corrected, appealed, or not resubmitted",
            "confidence": 0.78,
            "priority": "MEDIUM",
        })

        suggestions["prevention_tips"].append({
            "tip": "Run duplicate claim detection before clearinghouse submission",
            "priority": "HIGH",
        })

    def _cob_suggestions(self, claim, suggestions):
        suggestions["suggested_corrections"].append({
            "field": "coordination_of_benefits",
            "suggested": "Verify primary and secondary payer order and update COB information",
            "confidence": 0.76,
            "priority": "HIGH",
        })

        suggestions["prevention_tips"].append({
            "tip": "Check COB and payer sequencing before claim submission",
            "priority": "MEDIUM",
        })

    def _coverage_suggestions(self, claim, suggestions):
        suggestions["suggested_corrections"].append({
            "field": "payer",
            "suggested": "Verify patient coverage, payer routing, and plan benefits",
            "confidence": 0.72,
            "priority": "HIGH",
        })

        suggestions["documentation_gaps"].append({
            "field": "coverage_documentation",
            "suggested": "Attach coverage or eligibility proof if available",
            "confidence": 0.68,
            "priority": "MEDIUM",
        })

        suggestions["prevention_tips"].append({
            "tip": "Run local eligibility pre-check and payer rule validation before submission",
            "priority": "HIGH",
        })

    def _diagnosis_inconsistent_suggestions(self, claim, suggestions):
        suggestions["icd_suggestions"].append({
            "field": "icd_codes",
            "suggested": "Review ICD-to-CPT compatibility and update diagnosis if supported by documentation",
            "confidence": 0.78,
            "priority": "HIGH",
        })

        suggestions["documentation_gaps"].append({
            "field": "clinical_documentation",
            "suggested": "Attach clinical note supporting diagnosis and billed procedure",
            "confidence": 0.72,
            "priority": "HIGH",
        })

    def _unknown_denial_suggestions(self, classification, suggestions):
        suggestions["suggested_corrections"].append({
            "field": "denial_reason",
            "suggested": "Review payer EOB/ERA denial reason and route to billing specialist",
            "confidence": 0.55,
            "priority": "MEDIUM",
        })

        suggestions["prevention_tips"].append({
            "tip": "Map payer-specific denial codes to internal denial taxonomy",
            "priority": "MEDIUM",
        })

# import time
# from datetime import datetime
# from typing import Any, Dict, List


# class AppealGenerator:
#     def generate(
#         self,
#         claim: Dict[str, Any],
#         analysis: Dict[str, Any]
#     ) -> Dict[str, Any]:
#         start_time = time.time()
#         claim = claim or {}
#         analysis = analysis or {}

#         patient = claim.get("patient", {}) or {}
#         provider = claim.get("provider", {}) or {}
#         payer = claim.get("payer", {}) or {}

#         claim_id = claim.get("claim_id", "UNKNOWN")

#         print("\n" + "-" * 80)
#         print("📝 [AppealGenerator] STARTED")
#         print(f"🧾 Claim ID: {claim_id}")
#         print(f"📌 Denial code: {analysis.get('denial_code', 'UNKNOWN')}")
#         print(f"📂 Category: {analysis.get('category', 'unknown')}")

#         denial_code = analysis.get("denial_code", "UNKNOWN")
#         denial_category = analysis.get("category", "unknown")
#         root_cause = analysis.get(
#             "root_cause",
#             analysis.get("denial_reason", "Denied claim")
#         )

#         retry_probability = self._safe_probability(
#             analysis.get("retry_probability"),
#             0.45,
#         )

#         appeal_priority = self._appeal_priority(retry_probability)

#         appeal_summary = analysis.get("appeal_summary") or (
#             f"We request reconsideration of claim {claim_id}, denied with code "
#             f"{denial_code}. The claim has been reviewed for {root_cause}."
#         )

#         service_date = (
#             claim.get("service_date")
#             or claim.get("date_of_service")
#             or self._first_service_date(claim)
#             or "N/A"
#         )

#         cpt_codes = self._codes_from_claim(claim, "cpt")
#         icd_codes = self._codes_from_claim(claim, "icd")

#         total_charge = (
#             claim.get("total_charge")
#             or claim.get("claim_amount")
#             or claim.get("amount")
#             or "N/A"
#         )

#         supporting_documents = self._supporting_documents(analysis)

#         appeal_text = f"""Date: {datetime.utcnow().strftime("%Y-%m-%d")}

# To: {payer.get("name", "Payer Appeals Department")}

# Re: Appeal for Claim {claim_id}
# Patient: {patient.get("name", "Unknown")}
# DOB: {patient.get("dob", "N/A")}
# Provider: {provider.get("name", "Provider")} / NPI {provider.get("npi", "N/A")}
# Service Date: {service_date}
# CPT Codes: {", ".join(cpt_codes) if cpt_codes else "N/A"}
# ICD Codes: {", ".join(icd_codes) if icd_codes else "N/A"}
# Claim Amount: {total_charge}
# Denial Code: {denial_code}
# Denial Category: {denial_category}

# Dear Appeals Reviewer,

# {appeal_summary}

# Root Cause Reviewed:
# - {root_cause}

# Corrective Actions:
# {self._format_actions(analysis)}

# Supporting Documentation Recommended:
# {self._format_list(supporting_documents)}

# Requested Action:
# Please reprocess this claim with the updated information and supporting documentation.

# Sincerely,
# Revenue Cycle Team
# """
#         duration_seconds = round(time.time() - start_time, 2)
       
#         print("✅ [AppealGenerator] COMPLETED")
#         print(f"📌 Appeal priority: {appeal_priority}")
#         print(f"📄 Supporting documents: {len(supporting_documents)}")
#         print(f"⏱️ Appeal generation duration: {duration_seconds}s")
#         print("-" * 80 + "\n")
#         return {
#             "appeal_summary": appeal_summary,
#             "appeal_text": appeal_text,
#             "status": "DRAFT",
#             "appeal_priority": appeal_priority,
#             "retry_probability": retry_probability,
#             "retry_probability_percent": round(retry_probability * 100),
#             "supporting_documents": supporting_documents,
#             "generated_at": datetime.utcnow().isoformat(),
#             "denial_code": denial_code,
#             "denial_category": denial_category,
#             "duration_seconds": duration_seconds,
#         }
      

#     def _format_actions(self, analysis: Dict[str, Any]) -> str:
#         corrections = []
#         corrections.extend(analysis.get("corrections", []) or [])
#         corrections.extend(analysis.get("suggested_corrections", []) or [])
#         corrections.extend(analysis.get("modifier_suggestions", []) or [])
#         corrections.extend(analysis.get("icd_suggestions", []) or [])
#         corrections.extend(analysis.get("cpt_corrections", []) or [])

#         formatted = []

#         for item in corrections:
#             if isinstance(item, dict):
#                 field = item.get("field", "claim")
#                 suggested = (
#                     item.get("suggested")
#                     or item.get("recommendation")
#                     or item.get("code")
#                     or "Review and correct as needed"
#                 )

#                 formatted.append(f"- {field}: {suggested}")

#             elif isinstance(item, str):
#                 formatted.append(f"- {item}")

#             else:
#                 formatted.append(f"- {str(item)}")

#         if not formatted:
#             formatted.append(
#                 "- Review denial reason, payer policy, and supporting documentation before appeal."
#             )

#         return "\n".join(formatted)

#     def _supporting_documents(self, analysis: Dict[str, Any]) -> List[str]:
#         documents = []

#         for item in analysis.get("documentation_gaps", []) or []:
#             if isinstance(item, dict):
#                 suggested = (
#                     item.get("suggested")
#                     or item.get("field")
#                     or item.get("reason")
#                 )
#                 if suggested:
#                     documents.append(str(suggested))
#             elif item:
#                 documents.append(str(item))

#         category = analysis.get("category")

#         if category == "medical_necessity":
#             documents.extend([
#                 "Clinical notes supporting medical necessity",
#                 "Relevant LCD/NCD or payer policy reference",
#             ])

#         elif category == "authorization_missing":
#             documents.extend([
#                 "Prior authorization approval",
#                 "Referral or precertification documentation",
#             ])

#         elif category == "timely_filing":
#             documents.extend([
#                 "Proof of timely filing",
#                 "Original clearinghouse acceptance report",
#             ])

#         elif category == "missing_information":
#             documents.append("Corrected claim demographics or missing attachments")

#         if not documents:
#             documents.append("Payer denial letter or EOB/ERA")

#         return list(dict.fromkeys(documents))

#     def _format_list(self, items: List[str]) -> str:
#         if not items:
#             return "- No supporting documents listed"

#         return "\n".join([f"- {item}" for item in items])

#     def _codes_from_claim(self, claim: Dict[str, Any], code_type: str) -> List[str]:
#         keys = [
#             f"{code_type}_codes",
#             f"{code_type}s",
#             code_type,
#         ]

#         values = []

#         for key in keys:
#             raw = claim.get(key)

#             if isinstance(raw, list):
#                 values.extend(raw)
#             elif raw:
#                 values.append(raw)

#         for service in claim.get("services") or claim.get("line_items") or []:
#             if not isinstance(service, dict):
#                 continue

#             if code_type == "cpt":
#                 raw = (
#                     service.get("cpt")
#                     or service.get("cpt_code")
#                     or service.get("procedure_code")
#                     or service.get("hcpcs")
#                 )
#             else:
#                 raw = (
#                     service.get("icd")
#                     or service.get("icd_code")
#                     or service.get("diagnosis_code")
#                     or service.get("diagnosis")
#                 )

#             if raw:
#                 values.append(raw)

#         return list(dict.fromkeys([
#             str(value).upper().strip()
#             for value in values
#             if value
#         ]))

#     def _first_service_date(self, claim: Dict[str, Any]) -> str | None:
#         for service in claim.get("services") or claim.get("line_items") or []:
#             if not isinstance(service, dict):
#                 continue

#             service_date = (
#                 service.get("service_date")
#                 or service.get("from_date")
#                 or service.get("date_of_service")
#             )

#             if service_date:
#                 return service_date

#         return None

#     def _safe_probability(self, value, default: float) -> float:
#         try:
#             probability = float(value if value is not None else default)
#         except (TypeError, ValueError):
#             probability = default

#         if probability > 1:
#             probability = probability / 100

#         return max(0.0, min(1.0, probability))

#     def _appeal_priority(self, retry_probability: float) -> str:
#         if retry_probability >= 0.70:
#             return "HIGH"

#         if retry_probability >= 0.45:
#             return "MEDIUM"

#         return "LOW"

import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class AppealGenerator:
    def generate(
        self,
        claim: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        start_time = time.time()

        claim = claim or {}
        analysis = analysis or {}

        patient = self._safe_dict(claim.get("patient"))
        provider = self._safe_dict(claim.get("provider"))
        payer = self._safe_dict(claim.get("payer"))

        claim_id = claim.get("claim_id") or claim.get("submission_id") or "UNKNOWN"

        denial_code = (
            analysis.get("denial_code")
            or analysis.get("code")
            or claim.get("denial_code")
            or "UNKNOWN"
        )

        denial_category = (
            analysis.get("category")
            or analysis.get("denial_category")
            or "unknown"
        )

        root_cause = (
            analysis.get("root_cause")
            or analysis.get("denial_reason")
            or analysis.get("reason")
            or "Denied claim requires payer review"
        )

        retry_probability = self._safe_probability(
            analysis.get("retry_probability"),
            0.45,
        )

        appeal_priority = self._appeal_priority(retry_probability)

        print("\n" + "-" * 80)
        print("📝 [AppealGenerator] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📌 Denial code: {denial_code}")
        print(f"📂 Category: {denial_category}")
        print(f"📊 Retry probability: {retry_probability}")
        print("-" * 80)

        service_date = (
            claim.get("service_date")
            or claim.get("date_of_service")
            or self._first_service_date(claim)
            or "N/A"
        )

        cpt_codes = self._codes_from_claim(claim, "cpt")
        icd_codes = self._codes_from_claim(claim, "icd")

        total_charge = self._format_money(
            claim.get("total_charge")
            or claim.get("claim_amount")
            or claim.get("amount")
        )

        supporting_documents = self._supporting_documents(analysis)

        appeal_summary = analysis.get("appeal_summary") or (
            f"We request reconsideration of claim {claim_id}, denied with code "
            f"{denial_code}. The claim has been reviewed for the identified issue: "
            f"{root_cause}."
        )

        appeal_text = self._build_appeal_text(
            claim_id=claim_id,
            patient=patient,
            provider=provider,
            payer=payer,
            service_date=service_date,
            cpt_codes=cpt_codes,
            icd_codes=icd_codes,
            total_charge=total_charge,
            denial_code=denial_code,
            denial_category=denial_category,
            root_cause=root_cause,
            appeal_summary=appeal_summary,
            supporting_documents=supporting_documents,
            analysis=analysis,
        )

        duration_seconds = round(time.time() - start_time, 2)

        result = {
            "appeal_summary": appeal_summary,
            "appeal_text": appeal_text,
            "status": "DRAFT",
            "appeal_priority": appeal_priority,
            "retry_probability": retry_probability,
            "retry_probability_percent": round(retry_probability * 100),
            "supporting_documents": supporting_documents,
            "generated_at": datetime.utcnow().isoformat(),
            "denial_code": denial_code,
            "denial_category": denial_category,
            "root_cause": root_cause,
            "duration_seconds": duration_seconds,
        }

        print("✅ [AppealGenerator] COMPLETED")
        print(f"📌 Appeal priority: {appeal_priority}")
        print(f"📄 Supporting documents: {len(supporting_documents)}")
        print(f"⏱️ Appeal generation duration: {duration_seconds}s")
        print("-" * 80 + "\n")

        return result

    def _build_appeal_text(
        self,
        claim_id: str,
        patient: Dict[str, Any],
        provider: Dict[str, Any],
        payer: Dict[str, Any],
        service_date: str,
        cpt_codes: List[str],
        icd_codes: List[str],
        total_charge: str,
        denial_code: str,
        denial_category: str,
        root_cause: str,
        appeal_summary: str,
        supporting_documents: List[str],
        analysis: Dict[str, Any],
    ) -> str:
        payer_name = payer.get("name") or "Payer Appeals Department"
        patient_name = patient.get("name") or "Unknown"
        patient_dob = patient.get("dob") or "N/A"

        provider_name = provider.get("name") or "Provider"
        provider_npi = provider.get("npi") or "N/A"

        return f"""Date: {datetime.utcnow().strftime("%Y-%m-%d")}

To: {payer_name}

Re: Appeal for Claim {claim_id}
Patient: {patient_name}
DOB: {patient_dob}
Provider: {provider_name} / NPI {provider_npi}
Service Date: {service_date}
CPT Codes: {", ".join(cpt_codes) if cpt_codes else "N/A"}
ICD Codes: {", ".join(icd_codes) if icd_codes else "N/A"}
Claim Amount: {total_charge}
Denial Code: {denial_code}
Denial Category: {denial_category}

Dear Appeals Reviewer,

{appeal_summary}

Root Cause Reviewed:
- {root_cause}

Corrective Actions:
{self._format_actions(analysis)}

Supporting Documentation Recommended:
{self._format_list(supporting_documents)}

Requested Action:
Please reprocess this claim with the updated information and supporting documentation.

Sincerely,
Revenue Cycle Team
"""

    def _format_actions(self, analysis: Dict[str, Any]) -> str:
        corrections = []

        for key in [
            "corrections",
            "suggested_corrections",
            "modifier_suggestions",
            "icd_suggestions",
            "cpt_corrections",
        ]:
            value = analysis.get(key) or []
            if isinstance(value, list):
                corrections.extend(value)
            else:
                corrections.append(value)

        formatted = []

        for item in corrections:
            if isinstance(item, dict):
                field = item.get("field") or item.get("target") or "claim"
                suggested = (
                    item.get("suggested")
                    or item.get("recommendation")
                    or item.get("code")
                    or item.get("message")
                    or "Review and correct as needed"
                )

                confidence = item.get("confidence")
                if confidence is not None:
                    formatted.append(
                        f"- {field}: {suggested} "
                        f"(confidence: {self._format_confidence(confidence)})"
                    )
                else:
                    formatted.append(f"- {field}: {suggested}")

            elif isinstance(item, str) and item.strip():
                formatted.append(f"- {item.strip()}")

            elif item:
                formatted.append(f"- {str(item)}")

        if not formatted:
            formatted.append(
                "- Review denial reason, payer policy, claim coding, and supporting documentation before appeal."
            )

        return "\n".join(formatted)

    def _supporting_documents(self, analysis: Dict[str, Any]) -> List[str]:
        documents = []

        for item in analysis.get("documentation_gaps", []) or []:
            if isinstance(item, dict):
                suggested = (
                    item.get("suggested")
                    or item.get("field")
                    or item.get("reason")
                    or item.get("document")
                )
                if suggested:
                    documents.append(str(suggested))
            elif item:
                documents.append(str(item))

        category = analysis.get("category")

        if category == "medical_necessity":
            documents.extend([
                "Clinical notes supporting medical necessity",
                "Relevant LCD/NCD or payer policy reference",
                "Diagnosis-to-procedure medical necessity support",
            ])

        elif category == "authorization_missing":
            documents.extend([
                "Prior authorization approval",
                "Referral or precertification documentation",
                "Payer authorization reference number",
            ])

        elif category == "timely_filing":
            documents.extend([
                "Proof of timely filing",
                "Original clearinghouse acceptance report",
                "Submission timestamp or payer receipt confirmation",
            ])

        elif category == "missing_information":
            documents.extend([
                "Corrected claim demographics",
                "Missing attachments requested by payer",
            ])

        elif category == "bundling_or_modifier":
            documents.extend([
                "Procedure note supporting separately identifiable service",
                "Modifier support documentation",
                "NCCI or payer policy review notes",
            ])

        if not documents:
            documents.append("Payer denial letter or EOB/ERA")

        return list(dict.fromkeys(documents))

    def _format_list(self, items: List[str]) -> str:
        if not items:
            return "- No supporting documents listed"

        return "\n".join([f"- {item}" for item in items if item])

    def _codes_from_claim(self, claim: Dict[str, Any], code_type: str) -> List[str]:
        values = []

        if code_type == "cpt":
            keys = ["cpt_codes", "cpts", "cpt", "procedure_codes"]
            service_keys = ["cpt", "cpt_code", "procedure_code", "hcpcs"]

        elif code_type == "icd":
            keys = ["icd_codes", "icds", "icd", "diagnosis_codes", "diagnoses"]
            service_keys = ["icd", "icd_code", "diagnosis_code"]

        else:
            return []

        for key in keys:
            raw = claim.get(key)

            if isinstance(raw, list):
                values.extend(raw)
            elif raw:
                values.append(raw)

        for service in claim.get("services") or claim.get("line_items") or []:
            if not isinstance(service, dict):
                continue

            for service_key in service_keys:
                raw = service.get(service_key)
                if raw:
                    values.append(raw)
                    break

        return list(dict.fromkeys([
            str(value).upper().strip()
            for value in values
            if value
        ]))

    def _first_service_date(self, claim: Dict[str, Any]) -> Optional[str]:
        for service in claim.get("services") or claim.get("line_items") or []:
            if not isinstance(service, dict):
                continue

            service_date = (
                service.get("service_date")
                or service.get("date_of_service")
                or service.get("dos")
                or service.get("from_date")
                or service.get("service_from_date")
            )

            if service_date:
                return str(service_date)

        return None

    def _safe_probability(self, value, default: float) -> float:
        try:
            probability = float(value if value is not None else default)
        except (TypeError, ValueError):
            probability = default

        if probability > 1:
            probability = probability / 100

        return max(0.0, min(1.0, probability))

    def _appeal_priority(self, retry_probability: float) -> str:
        if retry_probability >= 0.70:
            return "HIGH"

        if retry_probability >= 0.45:
            return "MEDIUM"

        return "LOW"

    def _format_confidence(self, value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)

        if number <= 1:
            number *= 100

        return f"{round(number)}%"

    def _format_money(self, value) -> str:
        if value in (None, ""):
            return "N/A"

        try:
            amount = float(str(value).replace("$", "").replace(",", "").strip())
            return f"${amount:,.2f}"
        except (TypeError, ValueError):
            return str(value)

    def _safe_dict(self, value) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}
# from datetime import datetime
# import logging
# import time

# from app.agents.base.base_agent import BaseAgent
# from app.db.database import get_db
# from app.services.analytics_service import update_metrics
# from app.services.compliance_service import ComplianceService

# logger = logging.getLogger(__name__)


# def _as_ratio(value, default=1.0):
#     try:
#         number = float(value if value is not None else default)
#     except (TypeError, ValueError):
#         return default
#     return number / 100 if number > 1 else number


# def _first(*values):
#     for value in values:
#         if value not in (None, "", []):
#             return value
#     return None


# class ComplianceAgent(BaseAgent):
#     """
#     Compliance Agent.

#     HITL is reserved for actual compliance blockers. Normal patient demographics
#     such as DOB/address are expected claim fields and must not be treated as
#     PHI violations by themselves.
#     """

#     async def run(self, claim):
#         start_time = time.time()
#         claim = claim or {}
#         claim_id = claim.get("claim_id")
#         logger.info("Compliance validation started", extra={"claim_id": claim_id})

#         validation = claim.get("validation") or {}
#         extraction = claim.get("extraction") or {}
#         compliance_input = claim.get("compliance") or claim.get("compliance_results") or {}
#         validation_score = _as_ratio(
#             _first(validation.get("score"), validation.get("validation_score"), extraction.get("validation_score")),
#             1.0,
#         )
#         ocr_confidence = _as_ratio(
#             _first(extraction.get("extraction_confidence"), extraction.get("ocr_quality"), claim.get("confidence")),
#             1.0,
#         )

#         failures = []

#         def fail(rule, reason, severity="HIGH"):
#             normalized = str(severity or "LOW").upper()
#             if normalized not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
#                 normalized = "LOW"
#             failures.append({"rule": rule, "reason": reason, "severity": normalized})

#         if ocr_confidence < 0.85:
#             fail("OCR_001", f"OCR confidence below 85% ({round(ocr_confidence * 100)}%)", "LOW")

#         provider = claim.get("provider") or {}
#         npi = str(provider.get("npi") or claim.get("provider_npi") or "").strip()
#         if npi and (not npi.isdigit() or len(npi) != 10 or npi in {"0000000000", "9999999999"}):
#             fail("NPI_001", "Provider NPI is invalid", "CRITICAL")

#         for payer_failure in self._payer_rule_failures(claim):
#             fail(**payer_failure)

#         for fraud_failure in self._fraud_failures(claim):
#             fail(**fraud_failure)

#         for issue in compliance_input.get("issues") or []:
#             if isinstance(issue, dict):
#                 fail(issue.get("rule", "COMPLIANCE_ISSUE"), issue.get("reason") or issue.get("message"), issue.get("severity", "LOW"))
#             else:
#                 fail("COMPLIANCE_ISSUE", str(issue), "LOW")

#         for violation in compliance_input.get("hipaa_violations") or claim.get("hipaa_violations") or []:
#             fail("HIPAA_001", str(violation), "CRITICAL")

#         if compliance_input.get("authorization_required") and not (
#             claim.get("authorization_number") or claim.get("prior_auth_number") or claim.get("auth_number")
#         ):
#             fail("AUTH_001", "Authorization number missing", "HIGH")

#         hard_reject_failures = [f for f in failures if f.get("severity") == "CRITICAL"]
#         hitl_failures = [f for f in failures if f.get("severity") == "HIGH"]

#         medium_failures = [
#             f for f in failures
#             if f.get("severity") == "MEDIUM"
#         ]

#         low_failures = [
#             f for f in failures
#             if f.get("severity") == "LOW"
#         ]

#         hard_reject = bool(hard_reject_failures)
#         hitl_required = bool(hitl_failures) and not hard_reject
#         warning_only = bool(failures) and not hard_reject and not hitl_required

#         if hard_reject:
#             compliance_status = "HARD_REJECT"

#         elif hitl_required:
#             compliance_status = "HITL_REQUIRED"

#         elif warning_only:
#             compliance_status = "WARNING"

#         else:
#             compliance_status = "COMPLIANT"

#         primary_failure = (
#             hard_reject_failures[0]
#             if hard_reject_failures
#             else hitl_failures[0]
#             if hitl_failures
#             else medium_failures[0]
#             if medium_failures
#             else low_failures[0]
#             if low_failures
#             else None
#         )

#         reason = primary_failure["reason"] if primary_failure else None
#         failed_rule = primary_failure["rule"] if primary_failure else None
#         severity = primary_failure["severity"] if primary_failure else None
#         risk_score = min(1.0, 0.02 + len(failures) * 0.25)
#         issues = [failure["reason"] for failure in failures]

#         if hitl_required or hard_reject:
#             logger.warning({"claim_id": claim_id, "all_failures": failures})
#             logger.warning({
#                 "claim_id": claim_id,
#                 "failed_rule": failed_rule,
#                 "reason": reason,
#                 "ocr_confidence": ocr_confidence,
#                 "validation_score": validation_score,
#                 "severity": severity,
#             })

#         audit_data = {
#             "claim_id": claim_id,
#             "submission_id": claim.get("submission_id"),
#             "timestamp": datetime.utcnow().isoformat(),
#             "status": compliance_status,
#             "issues": issues,
#             "audit_details": {
#                 "checked_fields": ["ocr_confidence", "provider_npi", "payer_rules", "authorization", "hipaa"],
#                 "failed_rule": failed_rule,
#                 "reason": reason,
#                 "severity": severity,
#                 "ocr_confidence": ocr_confidence,
#                 "validation_score": validation_score,
#             },
#         }

#         db = next(get_db())
#         try:
#             ComplianceService(db).create_audit(audit_data)
#         finally:
#             db.close()
#         logger.info("Compliance audit stored", extra={"claim_id": claim_id, "status": compliance_status})

#         compliance_result = {
#             "passed": not hitl_required and not hard_reject,
#             "hard_reject": hard_reject,
#             "hitl_required": hitl_required,
#             "reason": reason,
#             "rule": failed_rule,
#             "severity": severity,
#             "risk_score": risk_score,
#             "ocr_confidence": ocr_confidence,
#             "validation_score": validation_score,
#             "issues": issues,
#         }

#         claim["compliance"] = compliance_result
#         claim["compliance_status"] = compliance_status
#         claim["compliance_failed"] = hitl_required or hard_reject
#         claim["hitl_required"] = hitl_required
#         claim["hard_reject"] = hard_reject

#         update_metrics(
#             event_type="compliance_failed" if hitl_required or hard_reject else "compliance_completed",
#             claim_id=claim_id,
#             agent="COMPLIANCE",
#             payer=claim.get("payer"),
#             risk_score=claim.get("risk_score", 0),
#             latency=time.time() - start_time,
#             status=compliance_status,
#         )

#         result_status = "HARD_REJECT" if hard_reject else "HITL_REQUIRED" if hitl_required else ("WARNING" if compliance_status == "WARNING" else "COMPLETED")

#         return {
#             "claim": claim,
#             "compliance_checked": True,
#             "status": result_status,
#             "compliance_status": compliance_status,
#             "passed": not hitl_required and not hard_reject,
#             "hard_reject": hard_reject,
#             "hitl_required": hitl_required,
#             "reason": reason,
#             "rule": failed_rule,
#             "severity": severity,
#             "risk_score": risk_score,
#             "compliance": compliance_result,
#             "audit": audit_data,
#         }

#     def _contains_phi(self, claim):
#         claim_str = str(claim).lower()
#         return "ssn" in claim_str or "social_security" in claim_str

#     def _validate_payer_rules(self, claim):
#         return not self._payer_rule_failures(claim)

#     def _payer_rule_failures(self, claim):
#         payer_rules = claim.get("payer_rules") or claim.get("coverage_criteria") or {}
#         if not isinstance(payer_rules, dict):
#             return []

#         failures = []
#         cpt_codes = self._codes_from_claim(claim, "cpt")
#         icd_codes = self._codes_from_claim(claim, "icd")
#         modifiers = {str(value).upper() for value in (claim.get("modifiers") or [])}
#         provider = claim.get("provider") or {}

#         allowed_cpts = {str(value).upper() for value in payer_rules.get("allowed_cpts") or payer_rules.get("covered_cpts") or []}
#         if allowed_cpts:
#             for cpt in cpt_codes:
#                 if cpt not in allowed_cpts:
#                     failures.append({"rule": "PAYER_CPT_001", "reason": f"CPT {cpt} is not allowed by payer", "severity": "HIGH"})

#         covered_icds = payer_rules.get("covered_icds") or payer_rules.get("icd_coverage") or {}
#         if isinstance(covered_icds, dict):
#             for cpt, covered in covered_icds.items():
#                 if str(cpt).upper() in cpt_codes and covered and not ({str(code).upper() for code in covered} & icd_codes):
#                     failures.append({"rule": "PAYER_ICD_001", "reason": f"No covered diagnosis found for CPT {cpt}", "severity": "HIGH"})

#         required_modifiers = payer_rules.get("required_modifiers") or {}
#         if isinstance(required_modifiers, dict):
#             for cpt, required in required_modifiers.items():
#                 required_set = {str(value).upper() for value in (required if isinstance(required, list) else [required])}
#                 if str(cpt).upper() in cpt_codes and required_set and not required_set.issubset(modifiers):
#                     failures.append({"rule": "PAYER_MOD_001", "reason": f"Required modifier missing for CPT {cpt}", "severity": "HIGH"})

#         if payer_rules.get("authorization_required") and not (
#             claim.get("authorization_number") or claim.get("prior_auth_number") or claim.get("auth_number")
#         ):
#             failures.append({"rule": "AUTH_001", "reason": "Authorization number missing", "severity": "HIGH"})

#         if payer_rules.get("network_required") and provider.get("in_network") is False:
#             failures.append({"rule": "PAYER_NETWORK_001", "reason": "Provider is out of network for payer", "severity": "HIGH"})

#         for edit in payer_rules.get("payer_specific_edits") or payer_rules.get("edits") or []:
#             if isinstance(edit, dict) and edit.get("failed"):
#                 failures.append({
#                     "rule": edit.get("rule", "PAYER_EDIT"),
#                     "reason": edit.get("reason") or edit.get("message") or "Payer-specific edit failed",
#                     "severity": str(edit.get("severity") or "HIGH").upper(),
#                 })

#         return failures

#     def _fraud_failures(self, claim):
#         failures = []
#         provider = claim.get("provider") or {}
#         payer_rules = claim.get("payer_rules") or {}
#         cpt_codes = self._codes_from_claim(claim, "cpt")
#         total_charge = self._number(claim.get("total_charge") or claim.get("claim_amount") or claim.get("amount"))

#         blacklisted = {str(value) for value in payer_rules.get("blacklisted_providers") or claim.get("blacklisted_providers") or []}
#         provider_npi = str(provider.get("npi") or claim.get("provider_npi") or "")
#         if provider.get("blacklisted") or provider_npi in blacklisted:
#             failures.append({"rule": "FRAUD_PROVIDER_001", "reason": "Provider is blacklisted", "severity": "CRITICAL"})

#         if claim.get("exact_duplicate") or claim.get("duplicate_claim") == "EXACT":
#             failures.append({"rule": "FRAUD_DUP_001", "reason": "Exact duplicate claim detected", "severity": "CRITICAL"})
#         elif claim.get("possible_duplicate") or claim.get("duplicate_claim"):
#             failures.append({"rule": "FRAUD_DUP_002", "reason": "Possible duplicate claim requires review", "severity": "HIGH"})

#         max_charge = self._number(payer_rules.get("max_charge") or 100000)
#         if total_charge and max_charge and total_charge > max_charge:
#             failures.append({"rule": "FRAUD_CHARGE_001", "reason": "Claim charge exceeds payer threshold", "severity": "CRITICAL"})

#         impossible_pairs = payer_rules.get("impossible_cpt_pairs") or [["99213", "99214"], ["93000", "93005"]]
#         for pair in impossible_pairs:
#             pair_set = {str(value).upper() for value in pair}
#             if pair_set and pair_set.issubset(cpt_codes):
#                 failures.append({"rule": "FRAUD_CPT_001", "reason": f"Suspicious CPT combination detected: {', '.join(sorted(pair_set))}", "severity": "CRITICAL"})

#         return failures

#     def _codes_from_claim(self, claim, code_type):
#         keys = [f"{code_type}_codes", f"{code_type}s", code_type]
#         values = []
#         for key in keys:
#             raw = claim.get(key)
#             if isinstance(raw, list):
#                 values.extend(raw)
#             elif raw:
#                 values.append(raw)
#         for service in claim.get("services") or claim.get("line_items") or []:
#             if isinstance(service, dict):
#                 raw = service.get(code_type) or service.get(f"{code_type}_code")
#                 if raw:
#                     values.append(raw)
#         return {str(value).upper().strip() for value in values if value}

#     def _number(self, value):
#         try:
#             return float(value or 0)
#         except (TypeError, ValueError):
#             return 0


from datetime import datetime
import logging
import time
import json

from app.agents.base.base_agent import BaseAgent
from app.db.database import get_db
from app.services.analytics_service import update_metrics
from app.services.compliance_service import ComplianceService
from app.utils.pipeline_events import send_pipeline_event
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


def _as_ratio(value, default=1.0):
    try:
        number = float(value if value is not None else default)
    except (TypeError, ValueError):
        return default

    return number / 100 if number > 1 else number


def _first(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


class ComplianceAgent(BaseAgent):
    """
    Compliance Agent.

    This agent checks:
    - OCR confidence
    - Provider NPI format
    - Payer-specific rules
    - Authorization requirements
    - HIPAA safety flags
    - Fraud / duplicate claim indicators
    - Suspicious CPT combinations
    - High charge thresholds

    Important:
    - Normal patient demographics like name, DOB, address are expected claim fields.
    - They should not be treated as HIPAA violations by themselves.
    """

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}
        claim_id = claim.get("claim_id")

        if not claim_id:
            raise ValueError("ComplianceAgent requires claim_id")

        print("\n" + "=" * 80)
        print("🛡️ [ComplianceAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        logger.info(
            "Compliance validation started",
            extra={"claim_id": claim_id}
        )

        await send_pipeline_event(
            manager,
            topic="compliance",
            action="running",
            claim_id=claim_id,
            stage="COMPLIANCE",
            status="RUNNING",
            progress=55,
            current_stage="COMPLIANCE",
            current_agent="ComplianceAgent",
            active_step="compliance",
            pipeline_state="COMPLIANCE_RUNNING",
            pipeline_status="RUNNING",
            message="Compliance Agent started",
        )

        validation = claim.get("validation") or {}
        extraction = claim.get("extraction") or {}
        compliance_input = (
            claim.get("compliance")
            or claim.get("compliance_results")
            or {}
        )

        validation_score = _as_ratio(
            _first(
                validation.get("score"),
                validation.get("validation_score"),
                extraction.get("validation_score"),
            ),
            1.0,
        )

        ocr_confidence = _as_ratio(
            _first(
                extraction.get("extraction_confidence"),
                extraction.get("ocr_quality"),
                claim.get("confidence"),
            ),
            1.0,
        )

        print("➡️ [1] Reading validation and OCR scores...")
        print(f"📊 Validation score ratio: {validation_score}")
        print(f"📄 OCR confidence ratio: {ocr_confidence}")
        print(f"📊 Validation score percent: {round(validation_score * 100)}%")
        print(f"📄 OCR confidence percent: {round(ocr_confidence * 100)}%")


        passed_rules = []
        failures = []

        def pass_rule(rule, label, message=None, value=None):
            passed = {
                "rule": rule,
                "label": label,
                "status": "PASSED",
                "message": message or f"{label} passed",
            }

            if value is not None:
                passed["value"] = value

            passed_rules.append(passed)

            print(f"✅ Compliance rule passed | Rule: {rule} | {passed['message']}")


        def fail(rule, reason, severity="HIGH", label=None, value=None):
            normalized = str(severity or "LOW").upper()

            if normalized not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                normalized = "LOW"

            failure = {
                "rule": rule,
                "label": label or rule,
                "status": "FAILED" if normalized in {"HIGH", "CRITICAL"} else "WARNING",
                "reason": reason,
                "message": reason,
                "severity": normalized,
            }

            if value is not None:
                failure["value"] = value

            failures.append(failure)

            print(
                f"🚨 Compliance failure added | "
                f"Rule: {rule} | Severity: {normalized} | Reason: {reason}"
            )

        # -------------------------------------------------
        # OCR confidence check
        # -------------------------------------------------
        print("➡️ [2] Checking OCR confidence...")

        if ocr_confidence < 0.85:
            fail(
                "OCR_001",
                f"OCR confidence below 85% ({round(ocr_confidence * 100)}%)",
                "LOW",
            )
        else:
            pass_rule(
                "OCR_001",
                "OCR confidence check",
                f"OCR confidence passed at {round(ocr_confidence * 100)}%",
                round(ocr_confidence * 100),
            )

        # -------------------------------------------------
        # Provider NPI check
        # -------------------------------------------------
        print("➡️ [3] Checking provider NPI...")

        provider = claim.get("provider") or {}
        npi = str(provider.get("npi") or claim.get("provider_npi") or "").strip()

        if npi and (
            not npi.isdigit()
            or len(npi) != 10
            or npi in {"0000000000", "9999999999"}
        ):
            fail("NPI_001", "Provider NPI is invalid", "CRITICAL")
        else:
            pass_rule(
                "NPI_001",
                "Provider NPI validation",
                "Provider NPI check passed or NPI not provided",
                npi or "not_provided",
            )
        # -------------------------------------------------
        # Payer rules
        # -------------------------------------------------
        print("➡️ [4] Checking payer-specific rules...")

        payer_failures = self._payer_rule_failures(claim)

        if payer_failures:
            print(f"🚨 Payer rule failures found: {len(payer_failures)}")
        else:
            pass_rule(
                "PAYER_RULES",
                "Payer-specific rules validation",
                "Payer-specific rules passed",
            )
        for payer_failure in payer_failures:
            fail(**payer_failure)

        # -------------------------------------------------
        # Fraud rules
        # -------------------------------------------------
        print("➡️ [5] Checking fraud / duplicate indicators...")

        fraud_failures = self._fraud_failures(claim)

        if fraud_failures:
            print(f"🚨 Fraud failures found: {len(fraud_failures)}")
        else:
            pass_rule(
                "FRAUD_DUPLICATE",
                "Fraud and duplicate claim check",
                "No fraud or duplicate indicators detected",
            )

        for fraud_failure in fraud_failures:
            fail(**fraud_failure)

        # -------------------------------------------------
        # HIPAA rules
        # -------------------------------------------------
        print("➡️ [6] Checking HIPAA safety rules...")

        hipaa_failures = self._hipaa_failures(claim)

        if hipaa_failures:
            print(f"🚨 HIPAA failures found: {len(hipaa_failures)}")
        else:
            pass_rule(
                "HIPAA_SAFETY",
                "HIPAA safety check",
                "HIPAA safety checks passed",
            )

        for hipaa_failure in hipaa_failures:
            fail(**hipaa_failure)

        # -------------------------------------------------
        # Existing compliance issues from upstream services
        # -------------------------------------------------
        print("➡️ [7] Checking upstream compliance issues...")

        upstream_issues = compliance_input.get("issues") or []

        if upstream_issues:
            print(f"🚨 Upstream compliance issues found: {len(upstream_issues)}")
        else:
            pass_rule(
                "UPSTREAM_COMPLIANCE",
                "Upstream compliance issue check",
                "No upstream compliance issues found",
            )

        for issue in upstream_issues:
            if isinstance(issue, dict):
                fail(
                    issue.get("rule", "COMPLIANCE_ISSUE"),
                    issue.get("reason") or issue.get("message") or "Upstream compliance issue found",
                    issue.get("severity", "LOW"),
                )
            else:
                fail("COMPLIANCE_ISSUE", str(issue), "LOW")

        # -------------------------------------------------
        # Authorization check
        # -------------------------------------------------


        print("➡️ [8] Checking authorization requirement...")

        claim_text = str(claim).lower()
        compliance_text = str(compliance_input).lower()
        validation_text = str(validation).lower()

        # Include optional extracted/raw document text if available.
        document_text = " ".join([
            str(claim.get("raw_text") or ""),
            str(claim.get("raw_ocr_text") or ""),
            str(claim.get("document_text") or ""),
            str(claim.get("extracted_text") or ""),
            str((claim.get("extraction") or {}).get("raw_text") or ""),
            str((claim.get("extraction") or {}).get("document_text") or ""),
        ]).lower()

        denial_text = str(claim.get("denial") or claim.get("denial_risk") or {}).lower()
        clearinghouse_text = str(claim.get("clearinghouse") or claim.get("clearinghouse_response") or {}).lower()

        combined_text = " ".join([
            claim_text,
            compliance_text,
            validation_text,
            document_text,
            denial_text,
            clearinghouse_text,
        ])

        auth_missing_phrases = [
            "auth_001",
            "prior authorization missing",
            "authorization missing",
            "authorization absent",
            "precertification absent",
            "precertification / authorization absent",
            "authorization was not obtained",
            "precertification/authorization absent",
            "precertification authorization absent",
            "authorization number missing",
        ]

        auth_required_phrases = [
            "prior authorization required",
            "authorization required",
            "precert required",
            "precertification required",
            "requires prior authorization",
            "requires authorization",
        ]

        authorization_required = (
            compliance_input.get("authorization_required") is True
            or claim.get("authorization_required") is True
            or claim.get("prior_authorization_required") is True
            or claim.get("precert_required") is True
            or any(phrase in combined_text for phrase in auth_missing_phrases)
            or any(phrase in combined_text for phrase in auth_required_phrases)
        )
    
        has_auth_number = self._valid_auth_number(
            claim.get("authorization_number")
            or claim.get("prior_auth_number")
            or claim.get("auth_number")
            or claim.get("prior_authorization")
            or claim.get("precert_number")
            or claim.get("prior_authorization_number")
        )

        auth_already_failed = any(
            failure.get("rule") == "AUTH_001"
            for failure in failures
        )

        if authorization_required and not has_auth_number and not auth_already_failed:
            fail(
                "AUTH_001",
                "Authorization number missing or precertification absent",
                "HIGH",
                label="Authorization requirement check",
                value="missing",
            )
        elif auth_already_failed:
            print("ℹ️ AUTH_001 already failed from payer/upstream rules")
        else:
            pass_rule(
                "AUTH_001",
                "Authorization requirement check",
                "Authorization check passed or authorization not required",
                has_auth_number or "not_required",
            )

        # -------------------------------------------------
        # Group failures by severity
        # -------------------------------------------------
        print("➡️ [9] Grouping failures by severity...")

        hard_reject_failures = [
            failure for failure in failures
            if failure.get("severity") == "CRITICAL"
        ]

        hitl_failures = [
            failure for failure in failures
            if failure.get("severity") == "HIGH"
        ]

        medium_failures = [
            failure for failure in failures
            if failure.get("severity") == "MEDIUM"
        ]

        low_failures = [
            failure for failure in failures
            if failure.get("severity") == "LOW"
        ]

        hard_reject = bool(hard_reject_failures)
        hitl_required = bool(hitl_failures) and not hard_reject
        warning_only = bool(failures) and not hard_reject and not hitl_required

        print(f"🚨 Critical failures: {len(hard_reject_failures)}")
        print(f"⚠️ High failures: {len(hitl_failures)}")
        print(f"🟡 Medium failures: {len(medium_failures)}")
        print(f"🔵 Low failures: {len(low_failures)}")

        if hard_reject:
            compliance_status = "HARD_REJECT"
        elif hitl_required:
            compliance_status = "HITL_REQUIRED"
        elif warning_only:
            compliance_status = "WARNING"
        else:
            compliance_status = "COMPLIANT"

        primary_failure = (
            hard_reject_failures[0]
            if hard_reject_failures
            else hitl_failures[0]
            if hitl_failures
            else medium_failures[0]
            if medium_failures
            else low_failures[0]
            if low_failures
            else None
        )

        reason = primary_failure["reason"] if primary_failure else None
        failed_rule = primary_failure["rule"] if primary_failure else None
        severity = primary_failure["severity"] if primary_failure else None

        # -------------------------------------------------
        # Severity-based risk score
        # -------------------------------------------------
        print("➡️ [10] Calculating compliance risk score...")

        severity_weight = {
            "LOW": 0.10,
            "MEDIUM": 0.25,
            "HIGH": 0.50,
            "CRITICAL": 0.90,
        }

        risk_score = min(
            1.0,
            sum(
                severity_weight.get(failure.get("severity"), 0.10)
                for failure in failures
            )
        )

        risk_score_percent = round(risk_score * 100)
        issues = [failure["reason"] for failure in failures]

        warning_rules = [
            failure for failure in failures
            if failure.get("severity") in {"LOW", "MEDIUM"}
        ]

        failed_rules = [
            failure for failure in failures
            if failure.get("severity") in {"HIGH", "CRITICAL"}
        ]

        executed_rules = passed_rules + warning_rules + failed_rules

        print(f"📊 Compliance risk score: {risk_score}")
        print(f"📊 Compliance risk score percent: {risk_score_percent}%")
        print(f"📌 Compliance status: {compliance_status}")

        if hitl_required or hard_reject:
            logger.warning({"claim_id": claim_id, "all_failures": failures})
            logger.warning({
                "claim_id": claim_id,
                "failed_rule": failed_rule,
                "reason": reason,
                "ocr_confidence": ocr_confidence,
                "validation_score": validation_score,
                "severity": severity,
            })

        # -------------------------------------------------
        # Duration
        # -------------------------------------------------
        duration_seconds = round(time.time() - start_time, 2)

        next_agent = (
            "Stop / Rejected"
            if hard_reject
            else "Case Orchestrator"
            if hitl_required
            else "Submission Agent"
        )

        result_status = (
            "HARD_REJECT"
            if hard_reject
            else "HITL_REQUIRED"
            if hitl_required
            else "WARNING"
            if compliance_status == "WARNING"
            else "COMPLETED"
        )


        review_required = bool(hitl_required or hard_reject)
        approval_required = bool(hitl_required)
        pipeline_paused = bool(hitl_required or hard_reject)

        if hard_reject:
            pipeline_state = "HARD_REJECT"
            pipeline_status = "HARD_REJECT"
            current_stage = "COMPLIANCE"
            current_agent = "ComplianceAgent"
            active_step = "compliance"
        elif hitl_required:
            pipeline_state = "HITL_REQUIRED"
            pipeline_status = "HITL_REQUIRED"
            current_stage = "COMPLIANCE"
            current_agent = "ComplianceAgent"
            active_step = "compliance"
        elif compliance_status == "WARNING":
            pipeline_state = "COMPLIANCE_WARNING"
            pipeline_status = "WARNING"
            current_stage = "COMPLIANCE"
            current_agent = "ComplianceAgent"
            active_step = "compliance"
        else:
            pipeline_state = "COMPLIANCE_COMPLETED"
            pipeline_status = "COMPLETED"
            current_stage = "COMPLIANCE"
            current_agent = "ComplianceAgent"
            active_step = "compliance"
        # -------------------------------------------------
        # Audit data
        # -------------------------------------------------
        print("➡️ [11] Building audit data...")

        audit_data = {
            "claim_id": claim_id,
            "submission_id": claim.get("submission_id"),
            "timestamp": datetime.utcnow().isoformat(),
            "status": compliance_status,
            "issues": issues,
            "duration_seconds": duration_seconds,
            "audit_details": {
                "checked_fields": [
                    "ocr_confidence",
                    "provider_npi",
                    "payer_rules",
                    "authorization",
                    "hipaa",
                    "fraud",
                    "duplicate",
                ],
                "passed_rules": passed_rules,
                "warning_rules": warning_rules,
                "failed_rules": failed_rules,
                "executed_rules": executed_rules,
                "passed_rule_count": len(passed_rules),
                "warning_rule_count": len(warning_rules),
                "failed_rule_count": len(failed_rules),
                "failed_rule": failed_rule,
                "reason": reason,
                "severity": severity,
                "ocr_confidence": ocr_confidence,
                "ocr_confidence_percent": round(ocr_confidence * 100),
                "validation_score": validation_score,
                "validation_score_percent": round(validation_score * 100),
                "risk_score": risk_score,
                "risk_score_percent": risk_score_percent,
            },
        }

        # -------------------------------------------------
        # Store audit
        # -------------------------------------------------
        print("➡️ [12] Storing compliance audit...")

        db_gen = get_db()
        db = next(db_gen)

        try:
            ComplianceService(db).create_audit(audit_data)
            print("✅ Compliance audit stored")
        except Exception as audit_error:
            print(f"❌ Compliance audit failed: {str(audit_error)}")
            logger.exception(
                "Compliance audit failed",
                extra={"claim_id": claim_id}
            )
        finally:
            db.close()

        logger.info(
            "Compliance audit stored",
            extra={"claim_id": claim_id, "status": compliance_status},
        )

        # -------------------------------------------------
        # Compliance result for claim/frontend
        # -------------------------------------------------
        compliance_result = {
            "claim_id": claim_id,
            "agent": "ComplianceAgent",
            "status": result_status,
            "compliance_status": compliance_status,
            "current_stage": current_stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "review_required": review_required,
            "approval_required": approval_required,
            "pipeline_paused": pipeline_paused,
            "passed": not hitl_required and not hard_reject,
            "hard_reject": hard_reject,
            "hitl_required": hitl_required,
            "warning_only": warning_only,
            "reason": reason,
            "rule": failed_rule,
            "severity": severity,
            "risk_score": risk_score,
            "risk_score_percent": risk_score_percent,
            "ocr_confidence": ocr_confidence,
            "ocr_confidence_percent": round(ocr_confidence * 100),
            "validation_score": validation_score,
            "validation_score_percent": round(validation_score * 100),
            "issues": issues,
            "failures": failures,

            # New frontend rule evidence
            "passed_rules": passed_rules,
            "warning_rules": warning_rules,
            "failed_rules": failed_rules,
            "executed_rules": executed_rules,
            "passed_rule_count": len(passed_rules),
            "warning_rule_count": len(warning_rules),
            "failed_rule_count": len(failed_rules),

            "audit": audit_data,
            "duration_seconds": duration_seconds,
            "next_agent": next_agent,
        }

        agent_detail_status = (
            "COMPLETED"
            if result_status == "COMPLETED"
            else "FAILED"
            if result_status == "HARD_REJECT"
            else "HITL"
            if result_status == "HITL_REQUIRED"
            else "WARNING"
        )

        agent_detail = self.build_agent_detail(
            "compliance",
            status=agent_detail_status,
            active_step="Compliance checks completed",
            message=f"Compliance status: {compliance_status}",
            started_at=started_at,
            duration_seconds=duration_seconds,
            passed=not hitl_required and not hard_reject,
            score=round(validation_score * 100),
            risk_score=risk_score,
            risk_score_percent=risk_score_percent,
            errors=issues if (hitl_required or hard_reject) else [],
            warnings=issues if not (hitl_required or hard_reject) else [],
            output=compliance_result,
            next_agent=next_agent,
        )
        agent_detail["passed_rules"] = passed_rules
        agent_detail["warning_rules"] = warning_rules
        agent_detail["failed_rules"] = failed_rules
        agent_detail["executed_rules"] = executed_rules
        agent_detail["passed_rule_count"] = len(passed_rules)
        agent_detail["warning_rule_count"] = len(warning_rules)
        agent_detail["failed_rule_count"] = len(failed_rules)
        
        # -------------------------------------------------
        # Store result on claim
        # -------------------------------------------------
        print("➡️ [13] Saving compliance result into claim...")

        claim["compliance"] = compliance_result
        claim["compliance_status"] = compliance_status
        claim["compliance_failed"] = hitl_required or hard_reject
        claim["hitl_required"] = hitl_required
        claim["hard_reject"] = hard_reject

        claim["review_required"] = review_required
        claim["approval_required"] = approval_required
        claim["pipeline_paused"] = pipeline_paused
        claim["pipeline_state"] = pipeline_state
        claim["pipeline_status"] = pipeline_status
        claim["current_stage"] = current_stage
        claim["current_agent"] = current_agent
        claim["active_step"] = active_step
        claim["progress"] = 60 if hitl_required else 55

        claim["compliance_duration_seconds"] = duration_seconds
        claim["compliance_risk_score"] = risk_score
        claim["compliance_risk_score_percent"] = risk_score_percent
        self.apply_agent_detail(
            claim,
            "compliance",
            agent_detail,
            step_completed=True,
            result_status=result_status,
        )

        print("✅ Compliance result saved to claim")
        print("📦 Compliance payload:")
        print(json.dumps(compliance_result, indent=2, default=str))

        # -------------------------------------------------
        # Metrics
        # -------------------------------------------------
        print("➡️ [14] Updating compliance metrics...")

        update_metrics(
            event_type=(
                "compliance_failed"
                if hitl_required or hard_reject
                else "compliance_completed"
            ),
            claim_id=claim_id,
            agent="COMPLIANCE",
            payer=claim.get("payer"),
            risk_score=risk_score,
            latency=duration_seconds,
            status=compliance_status,
        )

        # -------------------------------------------------
        # WebSocket event for frontend
        # -------------------------------------------------
        print("➡️ [15] Sending compliance event to frontend...")

        event_payload = self.build_agent_event_payload(
            "compliance",
            claim_id,
            agent_detail,
            existing_payload=compliance_result,
            result_status=result_status,
        )

        event_payload.update({
            "claim_id": claim_id,
            "stage": "COMPLIANCE",
            "status": result_status,
            "current_stage": current_stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "review_required": review_required,
            "approval_required": approval_required,
            "pipeline_paused": pipeline_paused,
            "progress": 60 if hitl_required else 55,
            "compliance": compliance_result,
            "hitl_required": hitl_required,
            "hard_reject": hard_reject,
        })

        await manager.send_event(
            "compliance",
            result_status.lower(),
            event_payload,
        )

        print("✅ Compliance event sent to frontend")
        print(f"✅ [ComplianceAgent] FINAL STATUS: {compliance_status}")
        print(f"⏱️ Compliance duration: {duration_seconds}s")
        print(f"⏭️ Next agent: {next_agent}")
        print("=" * 80 + "\n")

        return {
            "claim": claim,
            "pipeline": claim.get("pipeline", {"steps": {"compliance_checked": True}}),
            "compliance_checked": True,
            "status": result_status,
            "compliance_status": compliance_status,
            "passed": not hitl_required and not hard_reject,
            "hard_reject": hard_reject,
            "hitl_required": hitl_required,
            "review_required": review_required,
            "approval_required": approval_required,
            "pipeline_paused": pipeline_paused,
            "pipeline_state": pipeline_state,
            "pipeline_status": pipeline_status,
            "current_stage": current_stage,
            "current_agent": current_agent,
            "active_step": active_step,
            "reason": reason,
            "rule": failed_rule,
            "severity": severity,
            "risk_score": risk_score,
            "risk_score_percent": risk_score_percent,
            "duration_seconds": duration_seconds,
            "passed_rules": passed_rules,
            "warning_rules": warning_rules,
            "failed_rules": failed_rules,
            "executed_rules": executed_rules,
            "compliance": compliance_result,
            "audit": audit_data,
            "agent_detail": agent_detail,
        }

    def _valid_auth_number(self, value):
        if not value:
            return None

        value = str(value).strip()

        invalid_values = {
            "missing",
            "absent",
            "required",
            "not_required",
            "not required",
            "none",
            "null",
            "authorization",
            "orization",
            "precertification",
            "precert",
            "auth",
            "number",
            "no",
            "n/a",
            "na",
            "unknown",
        }

        value_lower = value.lower()

        if value_lower in invalid_values:
            return None

        if "missing" in value_lower or "absent" in value_lower:
            return None

        if not any(char.isdigit() for char in value):
            return None

        return value

    def _contains_phi(self, claim):
        claim_str = str(claim).lower()
        return "ssn" in claim_str or "social_security" in claim_str

    def _validate_payer_rules(self, claim):
        return not self._payer_rule_failures(claim)

    def _hipaa_failures(self, claim):
        failures = []

        raw_claim = str(claim).lower()

        sensitive_keys = [
            "ssn",
            "social_security",
            "social_security_number",
            "patient_ssn",
        ]

        for key in sensitive_keys:
            if key in raw_claim:
                failures.append({
                    "rule": "HIPAA_SSN_001",
                    "reason": "Possible SSN/social security field found in claim payload",
                    "severity": "CRITICAL",
                })
                break

        compliance_input = (
            claim.get("compliance")
            or claim.get("compliance_results")
            or {}
        )

        for violation in claim.get("hipaa_violations") or []:
            failures.append({
                "rule": "HIPAA_001",
                "reason": str(violation),
                "severity": "CRITICAL",
            })

        for violation in compliance_input.get("hipaa_violations") or []:
            failures.append({
                "rule": "HIPAA_001",
                "reason": str(violation),
                "severity": "CRITICAL",
            })

        if claim.get("raw_ocr_text") or claim.get("full_document_text"):
            failures.append({
                "rule": "HIPAA_MIN_001",
                "reason": "Raw OCR/full document text is present; avoid exposing full PHI payload to frontend or logs",
                "severity": "HIGH",
            })

        if claim.get("sent_to_external_llm") and not claim.get("deidentified_for_llm"):
            failures.append({
                "rule": "HIPAA_LLM_001",
                "reason": "PHI appears to be sent to external LLM/API without de-identification flag",
                "severity": "CRITICAL",
            })

        if claim.get("frontend_payload_contains_full_phi"):
            failures.append({
                "rule": "HIPAA_UI_001",
                "reason": "Frontend payload is marked as containing full PHI",
                "severity": "HIGH",
            })

        return failures

    def _payer_rule_failures(self, claim):
        payer_rules = claim.get("payer_rules") or claim.get("coverage_criteria") or {}

        if not isinstance(payer_rules, dict):
            return []

        failures = []
        cpt_codes = self._codes_from_claim(claim, "cpt")
        icd_codes = self._codes_from_claim(claim, "icd")
        modifiers = {
            str(value).upper()
            for value in (claim.get("modifiers") or [])
        }
        provider = claim.get("provider") or {}

        allowed_cpts = {
            str(value).upper()
            for value in (
                payer_rules.get("allowed_cpts")
                or payer_rules.get("covered_cpts")
                or []
            )
        }

        if allowed_cpts:
            for cpt in cpt_codes:
                if cpt not in allowed_cpts:
                    failures.append({
                        "rule": "PAYER_CPT_001",
                        "reason": f"CPT {cpt} is not allowed by payer",
                        "severity": "HIGH",
                    })

        covered_icds = (
            payer_rules.get("covered_icds")
            or payer_rules.get("icd_coverage")
            or {}
        )

        if isinstance(covered_icds, dict):
            for cpt, covered in covered_icds.items():
                covered_set = {
                    str(code).upper()
                    for code in covered
                }

                if (
                    str(cpt).upper() in cpt_codes
                    and covered
                    and not (covered_set & icd_codes)
                ):
                    failures.append({
                        "rule": "PAYER_ICD_001",
                        "reason": f"No covered diagnosis found for CPT {cpt}",
                        "severity": "HIGH",
                    })

        required_modifiers = payer_rules.get("required_modifiers") or {}

        if isinstance(required_modifiers, dict):
            for cpt, required in required_modifiers.items():
                required_set = {
                    str(value).upper()
                    for value in (
                        required
                        if isinstance(required, list)
                        else [required]
                    )
                }

                if (
                    str(cpt).upper() in cpt_codes
                    and required_set
                    and not required_set.issubset(modifiers)
                ):
                    failures.append({
                        "rule": "PAYER_MOD_001",
                        "reason": f"Required modifier missing for CPT {cpt}",
                        "severity": "HIGH",
                    })

        if payer_rules.get("authorization_required") and not (
            claim.get("authorization_number")
            or claim.get("prior_auth_number")
            or claim.get("auth_number")
            or claim.get("prior_authorization")
        ):
            failures.append({
                "rule": "AUTH_001",
                "reason": "Authorization number missing",
                "severity": "HIGH",
            })

        if payer_rules.get("network_required") and provider.get("in_network") is False:
            failures.append({
                "rule": "PAYER_NETWORK_001",
                "reason": "Provider is out of network for payer",
                "severity": "HIGH",
            })

        for edit in (
            payer_rules.get("payer_specific_edits")
            or payer_rules.get("edits")
            or []
        ):
            if isinstance(edit, dict) and edit.get("failed"):
                failures.append({
                    "rule": edit.get("rule", "PAYER_EDIT"),
                    "reason": (
                        edit.get("reason")
                        or edit.get("message")
                        or "Payer-specific edit failed"
                    ),
                    "severity": str(edit.get("severity") or "HIGH").upper(),
                })

        return failures

    def _fraud_failures(self, claim):
        failures = []

        provider = claim.get("provider") or {}
        payer_rules = claim.get("payer_rules") or {}
        cpt_codes = self._codes_from_claim(claim, "cpt")

        total_charge = self._number(
            claim.get("total_charge")
            or claim.get("claim_amount")
            or claim.get("amount")
        )

        blacklisted = {
            str(value)
            for value in (
                payer_rules.get("blacklisted_providers")
                or claim.get("blacklisted_providers")
                or []
            )
        }

        provider_npi = str(provider.get("npi") or claim.get("provider_npi") or "")

        if provider.get("blacklisted") or provider_npi in blacklisted:
            failures.append({
                "rule": "FRAUD_PROVIDER_001",
                "reason": "Provider is blacklisted",
                "severity": "CRITICAL",
            })

        if claim.get("exact_duplicate") or claim.get("duplicate_claim") == "EXACT":
            failures.append({
                "rule": "FRAUD_DUP_001",
                "reason": "Exact duplicate claim detected",
                "severity": "CRITICAL",
            })

        elif claim.get("possible_duplicate") or claim.get("duplicate_claim"):
            failures.append({
                "rule": "FRAUD_DUP_002",
                "reason": "Possible duplicate claim requires review",
                "severity": "HIGH",
            })

        max_charge = self._number(payer_rules.get("max_charge") or 100000)

        if total_charge and max_charge and total_charge > max_charge:
            failures.append({
                "rule": "FRAUD_CHARGE_001",
                "reason": "Claim charge exceeds payer threshold",
                "severity": "CRITICAL",
            })

        impossible_pairs = (
            payer_rules.get("impossible_cpt_pairs")
            or [["99213", "99214"], ["93000", "93005"]]
        )

        for pair in impossible_pairs:
            pair_set = {
                str(value).upper()
                for value in pair
            }

            if pair_set and pair_set.issubset(cpt_codes):
                failures.append({
                    "rule": "FRAUD_CPT_001",
                    "reason": (
                        "Suspicious CPT combination detected: "
                        f"{', '.join(sorted(pair_set))}"
                    ),
                    "severity": "CRITICAL",
                })

        return failures

    def _codes_from_claim(self, claim, code_type):
        keys = [f"{code_type}_codes", f"{code_type}s", code_type]
        values = []

        for key in keys:
            raw = claim.get(key)

            if isinstance(raw, list):
                values.extend(raw)
            elif raw:
                values.append(raw)

        for service in claim.get("services") or claim.get("line_items") or []:
            if isinstance(service, dict):
                raw = (
                    service.get(code_type)
                    or service.get(f"{code_type}_code")
                )

                if raw:
                    values.append(raw)

        return {
            str(value).upper().strip()
            for value in values
            if value
        }

    def _number(self, value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

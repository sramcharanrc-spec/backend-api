import time
import logging

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit

logger = logging.getLogger(__name__)


class EligibilityAgent(BaseAgent):
    """
    Eligibility Agent

    This agent performs a LOCAL eligibility pre-check only.

    Important:
    - It does NOT verify real payer coverage.
    - Payer API verification is marked as not_configured.
    - Data quality issues are returned as errors/warnings.
    - Agent technical failure is different from precheck_failed.
    """

    async def run(self, claim):
        start_time = time.time()
        started_at = self._utc_now()
        claim = claim or {}

        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "=" * 80)
        print("🧾 [EligibilityAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        try:
            patient = self._safe_dict(claim.get("patient"))
            payer = self._safe_dict(claim.get("payer"))
            provider = self._safe_dict(claim.get("provider"))
            insurance = self._safe_dict(claim.get("insurance"))

            services = claim.get("services") or []
            if not isinstance(services, list):
                services = []

            diagnosis_codes = (
                claim.get("diagnosis_codes")
                or claim.get("icd_codes")
                or []
            )

            cpt_codes = (
                claim.get("cpt_codes")
                or self._extract_cpt_codes(services)
                or []
            )

            total_charge = self._safe_float(claim.get("total_charge"))

            patient_name = (
                patient.get("name")
                or claim.get("patient_name")
            )

            patient_dob = (
                patient.get("dob")
                or patient.get("date_of_birth")
                or claim.get("patient_dob")
            )

            member_id = (
                patient.get("member_id")
                or insurance.get("member_id")
                or payer.get("member_id")
                or claim.get("member_id")
            )

            payer_name = (
                payer.get("name")
                or insurance.get("payer")
                or claim.get("payer_name")
            )

            payer_id = (
                payer.get("payer_id")
                or payer.get("id")
                or insurance.get("payer_id")
            )

            provider_name = (
                provider.get("name")
                or claim.get("provider_name")
            )

            provider_npi = (
                provider.get("npi")
                or provider.get("billing_npi")
                or claim.get("provider_npi")
            )

            provider_tax_id = (
                provider.get("tax_id")
                or claim.get("provider_tax_id")
            )

            service_date = self._extract_service_date(services)
            prior_authorization = (
                claim.get("prior_authorization")
                or claim.get("authorization")
            )

            print(f"👤 Patient: {patient}")
            print(f"💳 Payer: {payer}")
            print(f"🏥 Provider: {provider}")
            print(f"🧾 Service lines count: {len(services)}")
            print(f"🧬 Diagnosis codes: {diagnosis_codes}")
            print(f"🧾 CPT codes: {cpt_codes}")

            await manager.send_event("eligibility", "running", {
                "claim_id": claim_id,
                "agent": "EligibilityAgent",
                "stage": "ELIGIBILITY",
                "message": "Eligibility local pre-check started",
                "current_stage": "ELIGIBILITY",
                "current_agent": "EligibilityAgent",
                "active_step": "eligibility",
                "progress": 25,
                "pipeline_state": "ELIGIBILITY_RUNNING",
                "pipeline_status": "RUNNING",
                "claim": claim,
            })

            blocking_errors = []
            warnings = []

            # ---------------------------------------------------
            # Step 1: Claim-level fields
            # ---------------------------------------------------
            print("➡️ [1] Checking claim-level fields...")

            if not claim_id or claim_id == "UNKNOWN":
                blocking_errors.append("Missing claim ID")
                print("❌ Missing claim ID")
            else:
                print("✅ Claim ID present")

            # ---------------------------------------------------
            # Step 2: Patient fields
            # ---------------------------------------------------
            print("➡️ [2] Checking patient information...")

            if not patient_name:
                blocking_errors.append("Missing patient name")
                print("❌ Missing patient name")
            else:
                print(f"✅ Patient name: {patient_name}")

            if not patient_dob:
                blocking_errors.append("Missing patient DOB")
                print("❌ Missing patient DOB")
            else:
                print(f"✅ Patient DOB: {patient_dob}")

            if not member_id:
                blocking_errors.append("Missing member / insured ID")
                print("❌ Missing member / insured ID")
            else:
                print(f"✅ Member / insured ID: {member_id}")

            # ---------------------------------------------------
            # Step 3: Payer fields
            # ---------------------------------------------------
            print("➡️ [3] Checking payer information...")

            if not payer_name:
                blocking_errors.append("Missing payer name")
                print("❌ Missing payer name")
            else:
                print(f"✅ Payer name: {payer_name}")

            if not payer_id:
                warnings.append("Missing payer ID mapping")
                print("⚠️ Missing payer ID mapping")
            else:
                print(f"✅ Payer ID: {payer_id}")

            # ---------------------------------------------------
            # Step 4: Provider fields
            # ---------------------------------------------------
            print("➡️ [4] Checking provider information...")

            if not provider_name:
                warnings.append("Missing provider name")
                print("⚠️ Missing provider name")
            else:
                print(f"✅ Provider name: {provider_name}")

            if not provider_npi:
                blocking_errors.append("Missing provider NPI")
                print("❌ Missing provider NPI")
            else:
                print(f"✅ Provider NPI: {provider_npi}")

            if not provider_tax_id:
                warnings.append("Missing provider Tax ID")
                print("⚠️ Missing provider Tax ID")
            else:
                print(f"✅ Provider Tax ID: {provider_tax_id}")

            # ---------------------------------------------------
            # Step 5: Service and coding fields
            # ---------------------------------------------------
            print("➡️ [5] Checking service and coding information...")

            if not services:
                blocking_errors.append("No service lines found")
                print("❌ No service lines found")
            else:
                print(f"✅ Service lines found: {len(services)}")

            if not service_date:
                warnings.append("Missing service date")
                print("⚠️ Missing service date")
            else:
                print(f"✅ Service date: {service_date}")

            if not diagnosis_codes:
                blocking_errors.append("Missing diagnosis / ICD codes")
                print("❌ Missing diagnosis / ICD codes")
            else:
                print(f"✅ Diagnosis codes: {diagnosis_codes}")

            if not cpt_codes:
                blocking_errors.append("Missing CPT / procedure codes")
                print("❌ Missing CPT / procedure codes")
            else:
                print(f"✅ CPT / procedure codes: {cpt_codes}")

            if total_charge <= 0:
                warnings.append("Missing or zero total charge")
                print("⚠️ Missing or zero total charge")
            else:
                print(f"✅ Total charge: {total_charge}")

            # ---------------------------------------------------
            # Step 6: Payer API status
            # ---------------------------------------------------
            payer_api_warnings = [
                "Payer API is not configured",
                "Coverage was not verified with payer",
            ]

            warnings.extend([
                item for item in payer_api_warnings
                if item not in warnings
            ])

            # ---------------------------------------------------
            # Step 7: Decide local pre-check status
            # ---------------------------------------------------
            print("➡️ [6] Building eligibility decision...")

            duration_seconds = round(time.time() - start_time, 2)

            if blocking_errors:
                eligibility_status = "precheck_failed"
                message = (
                    "Local eligibility pre-check failed. "
                    "Real payer verification is not configured."
                )
                passed = False

            elif warnings:
                eligibility_status = "precheck_passed_with_warnings"
                message = (
                    "Local eligibility pre-check passed with warnings. "
                    "Real payer verification is not configured."
                )
                passed = True

            else:
                eligibility_status = "precheck_passed"
                message = (
                    "Local eligibility pre-check passed. "
                    "Real payer verification is not configured."
                )
                passed = True

            eligibility_payload = {
                "claim_id": claim_id,
                "agent": "EligibilityAgent",
                "status": eligibility_status,
                "eligibility_status": eligibility_status,
                "passed": passed,
                "payer_verification_status": "not_configured",
                "duration_seconds": duration_seconds,
                "message": message,
                "errors": blocking_errors,
                "warnings": warnings,
                "payer": {
                    "name": payer_name,
                    "payer_id": payer_id,
                },
                "patient": {
                    "name": patient_name,
                    "dob": patient_dob,
                    "member_id": member_id,
                    "address": patient.get("address"),
                    "city": patient.get("city"),
                    "state": patient.get("state"),
                    "zip": patient.get("zip"),
                },
                "provider": {
                    "name": provider_name,
                    "npi": provider_npi,
                    "tax_id": provider_tax_id,
                },
                "claim_summary": {
                    "service_date": service_date,
                    "diagnosis_codes": diagnosis_codes,
                    "cpt_codes": cpt_codes,
                    "prior_authorization": prior_authorization,
                    "total_charge": total_charge,
                    "service_count": len(services),
                },
                "current_stage": "ELIGIBILITY",
                "current_agent": "EligibilityAgent",
                "active_step": "eligibility",
                "progress": 25,
                "next_agent": "Validation Agent",
                "claim": claim,
            }

            print("📦 Eligibility payload:")
            print(eligibility_payload)

            # ---------------------------------------------------
            # Step 8: Save result into claim
            # ---------------------------------------------------
            print("➡️ [7] Saving eligibility result into claim...")

            claim["eligibility"] = eligibility_payload
            claim["eligibility_status"] = eligibility_status
            claim["payer_verification_status"] = "not_configured"
            claim["eligibility_errors"] = blocking_errors
            claim["eligibility_warnings"] = warnings
            claim["eligibility_duration_seconds"] = duration_seconds

            # Keep normalized values on claim
            claim.setdefault("patient", patient)
            claim.setdefault("payer", payer)
            claim.setdefault("provider", provider)

            if patient_name:
                claim["patient"]["name"] = patient_name

            if patient_dob:
                claim["patient"]["dob"] = patient_dob

            if member_id:
                claim["patient"]["member_id"] = member_id
                claim.setdefault("insurance", insurance)
                claim["insurance"]["member_id"] = member_id

            if payer_name:
                claim["payer"]["name"] = payer_name

            if payer_id:
                claim["payer"]["payer_id"] = payer_id

            if provider_name:
                claim["provider"]["name"] = provider_name

            if provider_npi:
                claim["provider"]["npi"] = provider_npi

            if provider_tax_id:
                claim["provider"]["tax_id"] = provider_tax_id

            detail_status = (
                "COMPLETED"
                if passed and not warnings
                else "WARNING"
            )

            agent_detail = self.build_agent_detail(
                "eligibility",
                status=detail_status,
                active_step="Eligibility local pre-check completed",
                message=message,
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=passed,
                errors=blocking_errors,
                warnings=warnings,
                output={
                    key: value
                    for key, value in eligibility_payload.items()
                    if key != "claim"
                },
                next_agent="Validation Agent",
            )
            self.apply_agent_detail(
                claim,
                "eligibility",
                agent_detail,
                step_completed=True,
                result_status=eligibility_status,
            )

            print(f"✅ Eligibility status: {eligibility_status}")
            print(f"⏱️ Eligibility duration: {duration_seconds}s")

            if blocking_errors:
                print("⚠️ [EligibilityAgent] COMPLETED WITH PRECHECK ERRORS")
                print(f"⚠️ Errors: {blocking_errors}")
            elif warnings:
                print("⚠️ [EligibilityAgent] COMPLETED WITH WARNINGS")
                print(f"⚠️ Warnings: {warnings}")
            else:
                print("✅ [EligibilityAgent] COMPLETED")

            # ---------------------------------------------------
            # Step 9: Audit
            # ---------------------------------------------------
            try:
                log_audit(
                    claim_id,
                    "eligibility",
                    "completed",
                    {
                        "eligibility_status": eligibility_status,
                        "payer_verification_status": "not_configured",
                        "errors": blocking_errors,
                        "warnings": warnings,
                        "duration_seconds": duration_seconds,
                    },
                )
                print("✅ Eligibility audit logged")

            except Exception as audit_error:
                print(f"⚠️ Eligibility audit failed: {str(audit_error)}")
                logger.exception("Eligibility audit failed")

            # ---------------------------------------------------
            # Step 10: Frontend event
            # ---------------------------------------------------
            await manager.send_event(
                "eligibility",
                "completed",
                self.build_agent_event_payload(
                    "eligibility",
                    claim_id,
                    agent_detail,
                    existing_payload=eligibility_payload,
                    result_status=eligibility_status,
                ),
            )

            print("✅ Eligibility event sent to frontend")
            print("=" * 80 + "\n")

            return {
                "claim": claim,
                "eligibility": eligibility_payload,
                "pipeline": {
                    "steps": {
                        "eligibility_checked": True,
                        "eligibility_passed": passed,
                    }
                },
                "stage": "eligibility_done",
                "status": eligibility_status,
                "duration_seconds": duration_seconds,
                "agent_detail": agent_detail,
            }

        except Exception as error:
            duration_seconds = round(time.time() - start_time, 2)

            print("❌ [EligibilityAgent] TECHNICAL FAILURE")
            print(f"❌ Error: {str(error)}")
            print(f"⏱️ Eligibility duration before failure: {duration_seconds}s")
            print("=" * 80 + "\n")

            logger.exception("EligibilityAgent failed")

            failure_payload = {
                "claim_id": claim_id,
                "agent": "EligibilityAgent",
                "status": "failed",
                "eligibility_status": "failed",
                "payer_verification_status": "not_configured",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "current_stage": "ELIGIBILITY",
                "current_agent": "EligibilityAgent",
                "active_step": "eligibility",
                "progress": 25,
                "claim": claim,
            }

            agent_detail = self.build_agent_detail(
                "eligibility",
                status="FAILED",
                active_step="Eligibility processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output={
                    key: value
                    for key, value in failure_payload.items()
                    if key != "claim"
                },
                next_agent="Case Orchestrator",
            )
            self.apply_agent_detail(
                claim,
                "eligibility",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )

            await manager.send_event(
                "eligibility",
                "failed",
                self.build_agent_event_payload(
                    "eligibility",
                    claim_id,
                    agent_detail,
                    existing_payload=failure_payload,
                    result_status="FAILED",
                    failed=True,
                    error=error,
                    duration_seconds=duration_seconds,
                ),
            )

            try:
                log_audit(
                    claim_id,
                    "eligibility",
                    "failed",
                    {
                        "error": str(error),
                        "duration_seconds": duration_seconds,
                    },
                )
            except Exception:
                logger.exception("Eligibility failure audit failed")

            return {
                "claim": claim,
                "eligibility": failure_payload,
                "pipeline": {
                    "steps": {
                        "eligibility_checked": False,
                        "eligibility_passed": False,
                    }
                },
                "stage": "eligibility_failed",
                "status": "FAILED",
                "error": str(error),
                "duration_seconds": duration_seconds,
                "agent_detail": agent_detail,
            }

    def _extract_service_date(self, services):
        for service in services or []:
            if not isinstance(service, dict):
                continue

            service_date = (
                service.get("service_date")
                or service.get("date_of_service")
                or service.get("dos")
                or service.get("date")
                or service.get("from_date")
                or service.get("service_from_date")
            )

            if service_date:
                return service_date

        return None

    def _extract_cpt_codes(self, services):
        codes = []

        for service in services or []:
            if not isinstance(service, dict):
                continue

            code = (
                service.get("cpt")
                or service.get("cpt_code")
                or service.get("procedure_code")
                or service.get("hcpcs")
            )

            if code:
                codes.append(str(code).strip())

        return list(dict.fromkeys(codes))

    def _safe_dict(self, value):
        return value if isinstance(value, dict) else {}

    def _safe_float(self, value):
        try:
            if value is None:
                return 0.0

            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()

            return float(value or 0)

        except (TypeError, ValueError):
            return 0.0

import time
import json

from app.agents.base.base_agent import BaseAgent
from app.websocket.manager import manager
from app.services.audit_service import log_audit
from app.agents.validation.rule_engine import run_all_rules
from app.utils.charge_validator import validate_charges
from app.utils.hybrid_validation import weighted_validation
from app.services.analytics_service import update_metrics
from app.db.database import SessionLocal
from app.utils.pipeline_events import send_pipeline_event
from app.services.enterprise_observability_service import (
    log_decision,
    validate_claim_enterprise,
)


class ValidationAgent(BaseAgent):

    async def run(self, state):
        start_time = time.time()
        started_at = self._utc_now()
        state = self.normalize_state(state)

        claim = state.get("claim", {}) or {}
        claim_id = claim.get("claim_id", "UNKNOWN")

        print("\n" + "=" * 80)
        print("🧪 [ValidationAgent] STARTED")
        print(f"🧾 Claim ID: {claim_id}")
        print(f"📥 Incoming state keys: {list(state.keys())}")
        print(f"📥 Incoming claim keys: {list(claim.keys())}")
        print("=" * 80)

        trace_id = await self.log_start("ValidationAgent", claim_id)

        print(f"🔎 Trace ID: {trace_id}")

        await send_pipeline_event(
            manager,
            topic="validation",
            action="running",
            claim_id=claim_id,
            stage="VALIDATION",
            status="RUNNING",
            progress=40,
            current_stage="VALIDATION",
            current_agent="ValidationAgent",
            active_step="validation",
            pipeline_state="VALIDATION_RUNNING",
            pipeline_status="RUNNING",
            message="Validation Agent started",
            extra={"trace_id": trace_id},
        )

        try:
            print("➡️ [1] Normalizing claim structure...")

            await self.log_step(
                "ValidationAgent",
                "Normalizing claim structure",
                trace_id=trace_id,
                claim_id=claim_id,
            )

            normalization_notes = []

            claim.setdefault("patient", {})
            claim.setdefault("provider", {})
            claim.setdefault("payer", {})
            claim.setdefault("services", [])

            patient = claim.get("patient") or {}
            provider = claim.get("provider") or {}
            payer = claim.get("payer") or {}
            services = claim.get("services") or []

            print("👤 Patient before normalization:", patient)
            print("🏥 Provider before normalization:", provider)
            print("💳 Payer before normalization:", payer)
            print(f"🧾 Services count: {len(services)}")

            # -------------------------------------------------
            # Normalize patient fields
            # -------------------------------------------------
            if not patient.get("name"):
                first_name = patient.get("first_name")
                last_name = patient.get("last_name")

                if first_name or last_name:
                    patient["name"] = " ".join(
                        [part for part in [first_name, last_name] if part]
                    ).strip()
                    print(f"✅ Patient name normalized: {patient['name']}")
                else:
                    normalization_notes.append("Missing patient name")
                    print("⚠️ Missing patient name")

            if not patient.get("dob") and patient.get("date_of_birth"):
                patient["dob"] = patient.get("date_of_birth")
                print(f"✅ Patient DOB normalized: {patient['dob']}")

            if not patient.get("dob"):
                normalization_notes.append("Missing patient DOB")
                print("⚠️ Missing patient DOB")

            # -------------------------------------------------
            # Normalize provider fields
            # -------------------------------------------------
            if not provider.get("npi") and claim.get("provider_npi"):
                provider["npi"] = claim.get("provider_npi")
                print(f"✅ Provider NPI normalized: {provider['npi']}")

            if not provider.get("tax_id") and claim.get("tax_id"):
                provider["tax_id"] = claim.get("tax_id")
                print(f"✅ Provider Tax ID normalized: {provider['tax_id']}")

            if not provider.get("name") and claim.get("provider_name"):
                provider["name"] = claim.get("provider_name")
                print(f"✅ Provider name normalized: {provider['name']}")

            provider_identifier = provider.get("npi") or provider.get("tax_id")

            if not provider_identifier:
                normalization_notes.append("Missing provider NPI or Tax ID")
                print("⚠️ Missing provider NPI or Tax ID")

            # -------------------------------------------------
            # Normalize payer fields
            # -------------------------------------------------
            if not payer.get("name") and claim.get("payer_name"):
                payer["name"] = claim.get("payer_name")
                print(f"✅ Payer name normalized: {payer['name']}")

            if not payer.get("name"):
                normalization_notes.append("Missing payer name")
                print("⚠️ Missing payer name")

            # -------------------------------------------------
            # Normalize services
            # -------------------------------------------------
            print("➡️ [2] Normalizing service lines...")

            for index, service in enumerate(services):
                if not isinstance(service, dict):
                    print(f"⚠️ Service line {index} is not a dict. Skipping.")
                    continue

                cpt = self._extract_cpt(service)

                print(f"🔹 Service #{index + 1} before:", service)

                if cpt and not service.get("cpt"):
                    service["cpt"] = cpt
                    print(f"✅ CPT normalized for service #{index + 1}: {cpt}")

                if service.get("units") not in (None, ""):
                    try:
                        service["units"] = int(service.get("units"))
                    except Exception:
                        normalization_notes.append(
                            f"Invalid units for CPT {cpt or 'UNKNOWN'}"
                        )
                        print(f"❌ Invalid units for CPT {cpt or 'UNKNOWN'}")

                if service.get("charge") not in (None, ""):
                    try:
                        service["charge"] = float(service.get("charge"))
                    except Exception:
                        normalization_notes.append(
                            f"Invalid charge for CPT {cpt or 'UNKNOWN'}"
                        )
                        print(f"❌ Invalid charge for CPT {cpt or 'UNKNOWN'}")

                print(f"🔹 Service #{index + 1} after:", service)

            # -------------------------------------------------
            # Normalize CPT codes
            # -------------------------------------------------
            print("➡️ [3] Extracting CPT codes...")

            if not claim.get("cpt_codes"):
                claim["cpt_codes"] = list({
                    self._extract_cpt(service)
                    for service in services
                    if isinstance(service, dict) and self._extract_cpt(service)
                })

            print("✅ CPT Codes:", claim.get("cpt_codes"))

            # -------------------------------------------------
            # Normalize ICD / diagnosis codes
            # -------------------------------------------------
            print("➡️ [4] Extracting ICD codes...")

            if not claim.get("icd_codes"):
                claim["icd_codes"] = (
                    claim.get("diagnosis_codes")
                    or claim.get("diagnoses")
                    or []
                )

            if not claim.get("icd_codes") and claim.get("diagnosis"):
                claim["icd_codes"] = [claim.get("diagnosis")]

            if not claim.get("icd_codes"):
                normalization_notes.append("Missing ICD codes")
                print("⚠️ Missing ICD codes")

            print("✅ ICD Codes:", claim.get("icd_codes"))

            # -------------------------------------------------
            # Required field validation
            # -------------------------------------------------
            print("➡️ [5] Checking required fields...")

            required_fields = {
                "patient.name": patient.get("name"),
                "patient.dob": patient.get("dob"),
                "provider.identifier": provider.get("npi") or provider.get("tax_id"),
                "payer.name": payer.get("name"),
                "services": services,
                "icd_codes": claim.get("icd_codes"),
                "cpt_codes": claim.get("cpt_codes"),
            }

            required_field_errors = []

            for field, value in required_fields.items():
                if not value:
                    error = f"Missing required field: {field}"
                    required_field_errors.append(error)
                    print(f"❌ {error}")
                else:
                    print(f"✅ Required field present: {field}")

            # -------------------------------------------------
            # Calculate total charge
            # -------------------------------------------------
            print("➡️ [6] Calculating total charge...")

            claim["total_charge"] = sum(
                self._safe_float(service.get("charge"))
                * self._safe_int(service.get("units"))
                for service in services
                if isinstance(service, dict)
            )

            print(f"💰 Total charge calculated: {claim['total_charge']}")

            if normalization_notes:
                print("⚠️ Normalization notes:", normalization_notes)

                await self.log_step(
                    "ValidationAgent",
                    "Normalization findings",
                    normalization_notes,
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                log_audit(
                    claim_id,
                    "normalization",
                    "findings",
                    {"findings": normalization_notes},
                )

            # -------------------------------------------------
            # Run rule validation
            # -------------------------------------------------
            print("➡️ [7] Running basic rule engine...")

            await self.log_step(
                "ValidationAgent",
                "Running validation rule engine",
                trace_id=trace_id,
                claim_id=claim_id,
            )

            rule_errors = run_all_rules(claim) or []
            print("📋 Rule engine errors:", rule_errors)

            charge_errors = validate_charges(claim)
            print("💰 Charge validation errors:", charge_errors)

            errors = rule_errors + charge_errors

            # -------------------------------------------------
            # Run weighted validation
            # -------------------------------------------------
            print("➡️ [8] Running weighted validation...")

            rule_result = weighted_validation(claim)

            print("📊 Weighted validation result:")
            print(json.dumps(rule_result, indent=2, default=str))

            # -------------------------------------------------
            # Run enterprise validation
            # -------------------------------------------------
            print("➡️ [9] Running enterprise validation...")

            enterprise_validation = {
                "cpt_valid": True,
                "icd_valid": True,
                "drug_match": True,
                "coverage_valid": True,
                "missing_fields": [],
                "warnings": [],
                "explanation": [],
                "rules_evaluated": [],
            }

            enterprise_explanation = []

            db = SessionLocal()

            try:
                enterprise_validation = validate_claim_enterprise(claim, db)
                enterprise_warnings = enterprise_validation.get("warnings") or []
                enterprise_explanation = (
                    enterprise_validation.get("explanation") or []
                )

                errors += [
                    warning
                    for warning in enterprise_warnings
                    if warning not in errors
                ]

            finally:
                db.close()

            print("🏢 Enterprise validation result:")
            print(json.dumps(enterprise_validation, indent=2, default=str))

            print("🧠 Enterprise explanation:", enterprise_explanation)

            await self.log_step(
                "ValidationAgent",
                "Validation errors detected",
                errors,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            await self.log_step(
                "ValidationAgent",
                "Weighted validation result",
                rule_result,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # -------------------------------------------------
            # Critical error detection
            # -------------------------------------------------
            print("➡️ [10] Detecting critical errors...")

            critical_keywords = [
                "no services",
                "zero charge",
                "invalid npi",
                "invalid dob",
                "invalid cpt",
                "missing",
            ]

            critical_errors = []
            critical_errors.extend(required_field_errors)

            critical_errors.extend([
                error
                for error in errors
                if any(keyword in str(error).lower() for keyword in critical_keywords)
            ])

            if not enterprise_validation.get("coverage_valid", True):
                critical_errors.append("Coverage validation failed")

            if not enterprise_validation.get("drug_match", True):
                critical_errors.append("Drug diagnosis compatibility failed")

            if not enterprise_validation.get("cpt_valid", True):
                critical_errors.append("CPT validity failed")

            if not enterprise_validation.get("icd_valid", True):
                critical_errors.append("ICD validity failed")

            critical_errors = list(dict.fromkeys(critical_errors))

            non_critical_errors = [
                error for error in errors if error not in critical_errors
            ]

            print("🚨 Critical errors:", critical_errors)
            print("⚠️ Non-critical errors:", non_critical_errors)

            # -------------------------------------------------
            # Failed rule mapping
            # -------------------------------------------------
            print("➡️ [11] Mapping failed rules...")

            failed_rules = []

            if required_field_errors:
                failed_rules.append("required_fields")

            if any("charge" in str(error).lower() for error in errors):
                failed_rules.append("charges")

            if any("service" in str(error).lower() for error in errors):
                failed_rules.append("services")

            if any("cpt" in str(error).lower() for error in errors):
                failed_rules.append("cpt_codes")

            if any("icd" in str(error).lower() for error in errors):
                failed_rules.append("icd_codes")

            if any("npi" in str(error).lower() for error in errors):
                failed_rules.append("provider_npi")

            if any("provider.identifier" in str(error).lower() for error in critical_errors):
                failed_rules.append("provider_identifier")

            if any("dob" in str(error).lower() for error in errors):
                failed_rules.append("patient_dob")

            if not enterprise_validation.get("coverage_valid", True):
                failed_rules.append("coverage_valid")

            if not enterprise_validation.get("drug_match", True):
                failed_rules.append("drug_match")

            if not enterprise_validation.get("cpt_valid", True):
                failed_rules.append("cpt_valid")

            if not enterprise_validation.get("icd_valid", True):
                failed_rules.append("icd_valid")

            rule_is_valid = bool(rule_result.get("is_valid", False))

            if not rule_is_valid:
                failed_rules.append("weighted_validation")

            failed_rules = list(dict.fromkeys(failed_rules))

            print("📌 Failed rules:", failed_rules)
            print(f"✅ Rule is valid: {rule_is_valid}")

            # -------------------------------------------------
            # Score calculation
            # -------------------------------------------------
            print("➡️ [12] Calculating validation scores...")

            extraction = claim.get("extraction") or {}

            try:
                claim_confidence = float(claim.get("confidence") or 0)
            except (TypeError, ValueError):
                claim_confidence = 0

            extraction_confidence = int(
                extraction.get("extraction_confidence")
                or round(claim_confidence * 100)
                or 0
            )

            service_confidence = int(extraction.get("service_confidence") or 0)

            field_completion = int(extraction.get("field_completion") or 0)

            if not field_completion:
                required_values = [
                    patient.get("name"),
                    patient.get("dob"),
                    provider.get("npi") or provider.get("tax_id"),
                    payer.get("name"),
                    services,
                    claim.get("total_charge"),
                ]

                field_completion = round(
                    sum(1 for value in required_values if value)
                    / len(required_values)
                    * 100
                )

            raw_validation_score = float(
                extraction.get("validation_score")
                or rule_result.get("score", 0)
            )

            if raw_validation_score <= 1:
                validation_score = round(raw_validation_score * 100)
            else:
                validation_score = round(raw_validation_score)

            risk_score = int(
                extraction.get("risk_score")
                or max(0, 100 - validation_score)
            )

            try:
                confidence = float(claim.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0

            print(f"📊 Claim confidence: {confidence}")
            print(f"📊 Extraction confidence: {extraction_confidence}")
            print(f"📊 Field completion: {field_completion}")
            print(f"📊 Service confidence: {service_confidence}")
            print(f"📊 Validation score: {validation_score}")
            print(f"📊 Risk score: {risk_score}")

            # -------------------------------------------------
            # Final validation mode
            # -------------------------------------------------
            if confidence < 0.5:
                validation_mode = "RULE_BASED"
                print("🧠 Validation mode: RULE_BASED")

                await self.log_step(
                    "ValidationAgent",
                    "Low confidence; using rule-based decision",
                    {"confidence": confidence},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )
            else:
                validation_mode = "AI + RULES"
                print("🧠 Validation mode: AI + RULES")

                await self.log_step(
                    "ValidationAgent",
                    "High confidence; using AI + rules decision",
                    {"confidence": confidence},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

            # Final decision
            is_valid = len(critical_errors) == 0 and rule_is_valid

            print("➡️ [13] Final validation decision")
            print(f"✅ Is valid: {is_valid}")
            print(f"🚨 Critical error count: {len(critical_errors)}")
            print(f"📌 Failed rule count: {len(failed_rules)}")
            print(f"⏭️ Next agent: {'Compliance Agent' if is_valid else 'Case Orchestrator'}")

            await self.log_step(
                "ValidationAgent",
                "Validation decision",
                {
                    "is_valid": is_valid,
                    "mode": validation_mode,
                    "critical_errors": critical_errors,
                    "non_critical_errors": non_critical_errors,
                },
                trace_id=trace_id,
                claim_id=claim_id,
            )

            # -------------------------------------------------
            # Save state
            # -------------------------------------------------
            print("➡️ [14] Saving validation result into state and claim...")

            state["claim"] = claim
            state.setdefault("pipeline", {})
            state["pipeline"].setdefault("steps", {})
            state["pipeline"]["steps"]["rules_validated"] = is_valid

            state["validation"] = {
                "valid": is_valid,
                "status": "passed" if is_valid else "failed",
                "mode": validation_mode,
                "score": rule_result.get("score", 0),
                "validation_score": validation_score,
                "extraction_confidence": extraction_confidence,
                "field_completion": field_completion,
                "service_confidence": service_confidence,
                "service_extraction": service_confidence,
                "ocr_quality": extraction.get("ocr_quality", 0),
                "risk_score": risk_score,
                "errors": errors,
                "critical_errors": critical_errors,
                "non_critical_errors": non_critical_errors,
                "required_field_errors": required_field_errors,
                "components": rule_result.get("components", {}),
                "weights": rule_result.get("weights", {}),
                "failed_rules": failed_rules,
                "validation_result": {
                    **enterprise_validation,
                    "failed_rules": failed_rules,
                },
                "explanation": enterprise_explanation,
                "next_agent": (
                    "Compliance Agent" if is_valid else "Case Orchestrator"
                ),
            }

            state["validation_result"] = state["validation"]

            claim["validation"] = state["validation"]
            claim["validation_status"] = "passed" if is_valid else "failed"
            claim["validation_score"] = validation_score
            claim["risk_score"] = risk_score

            print("✅ Validation saved to state['validation']")
            print("✅ Validation saved to claim['validation']")

            # -------------------------------------------------
            # Log enterprise decision
            # -------------------------------------------------
            print("➡️ [15] Logging enterprise validation decision...")

            db = SessionLocal()

            try:
                log_decision(
                    db,
                    claim_id,
                    "ValidationAgent",
                    {
                        "claim_id": claim_id,
                        "cpt_codes": claim.get("cpt_codes"),
                        "icd_codes": claim.get("icd_codes"),
                        "payer": claim.get("payer"),
                        "services": claim.get("services"),
                    },
                    enterprise_validation.get("rules_evaluated", []),
                    "VALID" if is_valid else "HITL_REQUIRED",
                    "; ".join(enterprise_explanation)
                    or ("Validation passed" if is_valid else "Validation failed"),
                )
                db.commit()
                print("✅ Enterprise decision logged")

            except Exception as db_error:
                db.rollback()
                print(f"❌ Enterprise decision log failed: {str(db_error)}")

            finally:
                db.close()

            # -------------------------------------------------
            # Broadcast scoring update
            # -------------------------------------------------
            print("➡️ [16] Broadcasting validation_scored event...")

            await manager.broadcast({
                "event": "validation_scored",
                "type": "validation_scored",
                "claim_id": claim_id,
                "stage": "VALIDATION",
                "status": "RUNNING",
                "current_stage": "VALIDATION",
                "progress": 35,
                "validation_score": validation_score,
                "extraction_confidence": extraction_confidence,
                "field_completion": field_completion,
                "service_confidence": service_confidence,
                "risk_score": risk_score,
                "claim": claim,
                "validation": state["validation"],
            })

            duration_seconds = round(time.time() - start_time, 2)

            validation_payload = {
                "claim_id": claim_id,
                "agent": "ValidationAgent",
                "status": "completed" if is_valid else "failed",
                "validation_status": "passed" if is_valid else "failed",
                "valid": is_valid,
                "mode": validation_mode,
                "validation_score": validation_score,
                "risk_score": risk_score,
                "duration_seconds": duration_seconds,
                "extraction_confidence": extraction_confidence,
                "field_completion": field_completion,
                "service_confidence": service_confidence,
                "errors": errors,
                "critical_errors": critical_errors,
                "non_critical_errors": non_critical_errors,
                "required_field_errors": required_field_errors,
                "failed_rules": failed_rules,
                "warnings": enterprise_validation.get("warnings", []),
                "reasoning": "; ".join(enterprise_explanation)
                or ("Validation passed" if is_valid else "Validation failed"),
                "output": {
                    "validation_result": enterprise_validation,
                    "components": rule_result.get("components", {}),
                    "weights": rule_result.get("weights", {}),
                },
                "progress": 100,
                "next_agent": "Compliance Agent" if is_valid else "Case Orchestrator",
                "trace_id": trace_id,
            }

            agent_detail = self.build_agent_detail(
                "validation",
                status="COMPLETED" if is_valid else "FAILED",
                active_step=(
                    "Validation passed"
                    if is_valid
                    else "Validation failed and requires review"
                ),
                message=(
                    "Validation passed"
                    if is_valid
                    else "Validation failed; routing to review"
                ),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=is_valid,
                score=validation_score,
                risk_score=risk_score,
                risk_score_percent=risk_score,
                errors=critical_errors if not is_valid else [],
                warnings=non_critical_errors + (enterprise_validation.get("warnings") or []),
                output=validation_payload,
                next_agent="Compliance Agent" if is_valid else "Case Orchestrator",
            )
            self.apply_agent_detail(
                claim,
                "validation",
                agent_detail,
                step_completed=is_valid,
                result_status="COMPLETED" if is_valid else "FAILED",
                failed=not is_valid,
            )
            state["agent_detail"] = agent_detail
            state["agents"] = claim.get("agents", {})
            state["pipeline"] = claim.get("pipeline", state.get("pipeline", {}))

            print("📤 Validation payload prepared:")
            print(json.dumps(validation_payload, indent=2, default=str))

            # -------------------------------------------------
            # Failed validation path
            # -------------------------------------------------
            if not is_valid:
                print("⛔ [ValidationAgent] FAILED")
                print("⛔ Routing to Case Orchestrator / HITL")

                state["status"] = "HITL_REQUIRED"
                state["next"] = "case_orchestrator"
                state["stage"] = "HITL_REQUIRED"
                state["trace_id"] = trace_id

                await self.log_step(
                    "ValidationAgent",
                    "HITL triggered",
                    {"errors": errors},
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                await manager.send_event(
                    "validation",
                    "completed" if is_valid else "failed",
                    self.build_agent_event_payload(
                        "validation",
                        claim_id,
                        agent_detail,
                        existing_payload=validation_payload,
                        result_status="FAILED",
                        failed=True,
                        error="Validation failed",
                        duration_seconds=duration_seconds,
                    )
                )

                update_metrics(
                    event_type="validation_failed",
                    claim_id=claim_id,
                    agent="VALIDATION",
                    payer=claim.get("payer"),
                    risk_score=risk_score,
                    latency=time.time() - start_time,
                    status="FAILED",
                )

                await self.log_end(
                    "ValidationAgent",
                    "HITL_REQUIRED",
                    time.time() - start_time,
                    trace_id=trace_id,
                    claim_id=claim_id,
                )

                print(f"⏱️ Validation duration: {round(time.time() - start_time, 2)}s")
                print("=" * 80 + "\n")

                return state

            # -------------------------------------------------
            # Success path
            # -------------------------------------------------
            print("✅ [ValidationAgent] PASSED")
            print("✅ Routing to Compliance Agent")

            log_audit(claim_id, "validation", "passed", {
                "warnings": non_critical_errors,
                "trace_id": trace_id,
            })

            state["status"] = "SUCCESS"
            state["stage"] = "VALIDATED"
            state["trace_id"] = trace_id

            await manager.send_event(
                "validation",
                self.build_agent_event_payload(
                    "validation",
                    claim_id,
                    agent_detail,
                    existing_payload=validation_payload,
                    result_status="COMPLETED",
                ),
            )

            update_metrics(
                event_type="validation_completed",
                claim_id=claim_id,
                agent="VALIDATION",
                payer=claim.get("payer"),
                risk_score=risk_score,
                latency=time.time() - start_time,
                status="COMPLETED",
            )

            await self.log_end(
                "ValidationAgent",
                "SUCCESS",
                time.time() - start_time,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            print(f"⏱️ Validation duration: {round(time.time() - start_time, 2)}s")
            print("=" * 80 + "\n")

            return state

        except Exception as error:
            print("❌ [ValidationAgent] EXCEPTION")
            print(f"❌ Error: {str(error)}")
            print(f"❌ Claim ID: {claim_id}")

            await self.log_error(
                "ValidationAgent",
                error,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            log_audit(claim_id, "validation", "failed", {
                "error": str(error),
                "trace_id": trace_id,
            })

            state["status"] = "FAILED"
            state["stage"] = "FAILED"
            state["validation"] = {
                "valid": False,
                "status": "failed",
                "errors": [str(error)],
            }
            state["next"] = "finish"
            state["trace_id"] = trace_id

            duration_seconds = round(time.time() - start_time, 2)
            failure_payload = {
                "claim_id": claim_id,
                "validation_status": "failed",
                "error": str(error),
                "trace_id": trace_id,
                "next_agent": "None",
                "progress": 40,
            }
            agent_detail = self.build_agent_detail(
                "validation",
                status="FAILED",
                active_step="Validation processing failed",
                message=str(error),
                started_at=started_at,
                duration_seconds=duration_seconds,
                passed=False,
                errors=[str(error)],
                output=failure_payload,
                next_agent=None,
            )
            self.apply_agent_detail(
                claim,
                "validation",
                agent_detail,
                step_completed=False,
                result_status="FAILED",
                failed=True,
            )
            state["agent_detail"] = agent_detail
            state["agents"] = claim.get("agents", {})
            state["pipeline"] = claim.get("pipeline", state.get("pipeline", {}))

            await manager.send_event(
                "validation",
                "failed",
                self.build_agent_event_payload(
                    "validation",
                    claim_id,
                    agent_detail,
                    existing_payload=failure_payload,
                    result_status="FAILED",
                    failed=True,
                    error=error,
                    duration_seconds=duration_seconds,
                ),
            )

            update_metrics(
                event_type="validation_failed",
                claim_id=claim_id,
                agent="VALIDATION",
                payer=claim.get("payer"),
                risk_score=claim.get("risk_score", 0),
                latency=duration_seconds,
                status="FAILED",
            )

            await self.log_end(
                "ValidationAgent",
                "FAILED",
                duration_seconds,
                trace_id=trace_id,
                claim_id=claim_id,
            )

            print(f"⏱️ Validation duration before failure: {round(time.time() - start_time, 2)}s")
            print("=" * 80 + "\n")

            return state

    def _extract_cpt(self, service):
        if not isinstance(service, dict):
            return None

        return (
            service.get("cpt")
            or service.get("cpt_code")
            or service.get("procedure_code")
            or service.get("hcpcs")
        )

    def _safe_float(self, value):
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def _safe_int(self, value):
        try:
            return int(value or 1)
        except Exception:
            return 1

import asyncio
from typing import Any, Dict, List, Set

from sqlalchemy.orm import Session

from app.agents.ai_suggestions.auto_correct_agent import AutoCorrectAgent
from app.agents.ai_suggestions.suggestion_agent import AISuggestionAgent
from app.agents.validation.validation_agent import ValidationAgent
from app.agents.validation.rule_engine import run_all_rules
from app.db.database import SessionLocal
from app.models.ai_repair_model import AISuggestion, CorrectionHistory, RepairLog
from app.services.enterprise_observability_service import validate_claim_enterprise
from app.utils.charge_validator import validate_charges
from app.utils.hybrid_validation import weighted_validation
from app.websocket.manager import manager


class ClaimRepairEngine:
    def __init__(self, db: Session | None = None):
        self.db = db
        self.suggestion_agent = AISuggestionAgent()
        self.auto_correct_agent = AutoCorrectAgent()
        self.validation_agent = ValidationAgent()

    async def repair_and_retry(self, state: Dict[str, Any], max_retries: int = 1) -> Dict[str, Any]:
        claim = state.get("claim", state)
        claim_id = claim.get("claim_id", "UNKNOWN")
        await manager.send_event("claim_repair", {"agent": "CLAIM_REPAIR", "claim_id": claim_id, "status": "running"})

        retry_count = 0
        current = {
            **state,
            "validation_result": state.get("validation_result") or state.get("validation"),
            "retry_mode": True,
        }
        while retry_count < max_retries:
            try:
                current = await asyncio.wait_for(
                    self.suggestion_agent.run(current),
                    timeout=3,
                )
            except asyncio.TimeoutError:
                current["ai_suggestions"] = []
                await manager.send_event("ai_suggestion", {
                    "agent": "AI_SUGGESTION",
                    "claim_id": claim_id,
                    "status": "completed",
                    "progress": current.get("claim", claim).get("progress"),
                })
            self._store_suggestions(claim_id, current.get("ai_suggestions", []))

            current = await self.auto_correct_agent.run(current)
            self._store_corrections(claim_id, current.get("correction_history", []))

            validation_result = current.get("validation_result") or current.get("validation") or {}
            failed_rules = self._failed_rules(validation_result)
            if self._requires_hitl(current):
                current["validation"] = self._blocked_validation(
                    validation_result,
                    current.get("claim", claim).get("autocorrect_blocked_reason")
                    or "Auto-correction could not safely repair required fields",
                )
                current["validation_result"] = current["validation"]
                current["status"] = "WAITING_FOR_REVIEW"
                current["stage"] = "WAITING_FOR_REVIEW"
                retry_count += 1
                await manager.send_event("validation_retry", {
                    "agent": "VALIDATION_RETRY",
                    "claim_id": claim_id,
                    "status": "failed",
                    "retry_count": retry_count,
                    "rules": sorted(self._failed_rules(current["validation"])),
                })
                break
            await manager.send_event("validation_retry", {
                "agent": "VALIDATION_RETRY",
                "claim_id": claim_id,
                "status": "running",
                "retry_count": retry_count + 1,
                "rules": sorted(failed_rules),
            })
            if validation_result and current.get("retry_mode"):
                current["validation"] = self.rerun_validation(
                    current.get("claim", claim),
                    validation_result,
                    failed_rules,
                )
                current["validation_result"] = current["validation"]
                current.setdefault("pipeline", {}).setdefault("steps", {})["rules_validated"] = current["validation"].get("valid") is True
                current["status"] = "SUCCESS" if current["validation"].get("valid") is True else "HITL_REQUIRED"
                current["stage"] = "VALIDATED" if current["validation"].get("valid") is True else "HITL_REQUIRED"
            else:
                current = await self.validation_agent.run({"claim": current.get("claim", claim)})
            retry_count += 1
            await manager.send_event("validation_retry", {
                "agent": "VALIDATION_RETRY",
                "claim_id": claim_id,
                "status": "completed" if current.get("validation", {}).get("valid") is True else "failed",
                "retry_count": retry_count,
                "rules": sorted(failed_rules),
            })
            if current.get("validation", {}).get("valid") is True:
                break

        success = current.get("validation", {}).get("valid") is True
        repair_status = "SUCCESS" if success else "WAITING_FOR_REVIEW" if self._requires_hitl(current) else "HITL_REQUIRED"
        self._store_repair_log(claim_id, repair_status, retry_count, current)
        await manager.send_event("claim_repair", {
            "agent": "CLAIM_REPAIR",
            "claim_id": claim_id,
            "status": "completed" if success else "failed",
            "retry_count": retry_count,
        })
        return current

    def apply_suggestions(self, claim: Dict[str, Any], suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "claim": claim,
            "ai_suggestions": suggestions,
        }

    def _requires_hitl(self, state: Dict[str, Any]) -> bool:
        claim = state.get("claim", state)
        return bool(
            claim.get("requires_hitl")
            or claim.get("pipeline_state") == "WAITING_FOR_REVIEW"
            or state.get("status") == "WAITING_FOR_REVIEW"
        )

    def _blocked_validation(self, previous_validation: Dict[str, Any], reason: str) -> Dict[str, Any]:
        errors = list(dict.fromkeys([
            *(previous_validation.get("errors") or []),
            *(previous_validation.get("critical_errors") or []),
            reason,
        ]))
        failed_rules = sorted({*self._failed_rules(previous_validation), "provider_npi"})
        return {
            **previous_validation,
            "valid": False,
            "mode": "AUTO_CORRECT_BLOCKED",
            "errors": errors,
            "critical_errors": errors,
            "required_field_errors": previous_validation.get("required_field_errors") or [],
            "failed_rules": failed_rules,
            "validation_result": {
                **(previous_validation.get("validation_result") or {}),
                "failed_rules": failed_rules,
            },
        }

    def _failed_rules(self, validation: Dict[str, Any]) -> Set[str]:
        validation_result = validation.get("validation_result") if isinstance(validation.get("validation_result"), dict) else {}
        explicit = validation.get("failed_rules") or validation_result.get("failed_rules") or []
        failed = {str(rule) for rule in explicit if rule}
        errors = [
            *(validation.get("required_field_errors") or []),
            *(validation.get("critical_errors") or []),
            *(validation.get("errors") or []),
        ]
        for error in errors:
            text = str(error).lower()
            if "charge" in text:
                failed.add("charges")
            if "service" in text:
                failed.add("services")
            if "cpt" in text:
                failed.add("cpt_codes")
            if "icd" in text:
                failed.add("icd_codes")
            if "npi" in text:
                failed.add("provider_npi")
            if "dob" in text:
                failed.add("patient_dob")
            if "missing" in text:
                failed.add("required_fields")
        if not validation_result.get("coverage_valid", True):
            failed.add("coverage_valid")
        if not validation_result.get("drug_match", True):
            failed.add("drug_match")
        if not validation_result.get("cpt_valid", True):
            failed.add("cpt_valid")
        if not validation_result.get("icd_valid", True):
            failed.add("icd_valid")
        if validation.get("valid") is False and not failed:
            failed.add("weighted_validation")
        return failed

    def rerun_validation(self, claim: Dict[str, Any], previous_validation: Dict[str, Any], rules: Set[str]) -> Dict[str, Any]:
        rules = set(rules or self._failed_rules(previous_validation))
        patient = claim.setdefault("patient", {})
        provider = claim.setdefault("provider", {})
        payer = claim.setdefault("payer", {})
        services = claim.setdefault("services", [])
        if not claim.get("cpt_codes"):
            claim["cpt_codes"] = list({
                service.get("cpt")
                for service in services
                if isinstance(service, dict) and service.get("cpt")
            })

        errors: List[str] = []
        if "required_fields" in rules:
            required_fields = {
                "patient.name": patient.get("name"),
                "patient.dob": patient.get("dob"),
                "provider.npi": provider.get("npi"),
                "payer.name": payer.get("name"),
                "services": services,
                "icd_codes": claim.get("icd_codes"),
            }
            errors.extend(
                f"Missing required field: {field}"
                for field, value in required_fields.items()
                if value in (None, "", [], {})
            )
        if "services" in rules and not services:
            errors.append("No services found")
        if "cpt_codes" in rules and not claim.get("cpt_codes"):
            errors.append("Missing CPT codes")
        if "icd_codes" in rules and not claim.get("icd_codes"):
            errors.append("Missing ICD codes")
        if "provider_npi" in rules and not provider.get("npi"):
            errors.append("Missing provider NPI")
        if "patient_dob" in rules and not patient.get("dob"):
            errors.append("Missing patient DOB")
        if "charges" in rules:
            try:
                claim["total_charge"] = sum(
                    float(service.get("charge") or 0) * int(service.get("units") or 1)
                    for service in services
                    if isinstance(service, dict)
                )
            except Exception:
                pass
            errors.extend(validate_charges(claim))
        if "basic_rules" in rules:
            errors.extend(run_all_rules(claim) or [])

        rule_result = weighted_validation(claim)
        if "weighted_validation" in rules and not rule_result.get("is_valid", False):
            errors.append("Weighted validation failed")

        enterprise_validation = dict(previous_validation.get("validation_result") or {})
        enterprise_rules = {"coverage_valid", "drug_match", "cpt_valid", "icd_valid"}
        if rules.intersection(enterprise_rules):
            db = SessionLocal()
            try:
                enterprise_validation.update(validate_claim_enterprise(claim, db))
            finally:
                db.close()
        if "coverage_valid" in rules and not enterprise_validation.get("coverage_valid", True):
            errors.append("Coverage validation failed")
        if "drug_match" in rules and not enterprise_validation.get("drug_match", True):
            errors.append("Drug diagnosis compatibility failed")
        if "cpt_valid" in rules and not enterprise_validation.get("cpt_valid", True):
            errors.append("CPT validity failed")
        if "icd_valid" in rules and not enterprise_validation.get("icd_valid", True):
            errors.append("ICD validity failed")

        errors = list(dict.fromkeys(errors))
        remaining_failed_rules = self._failed_rules({
            **previous_validation,
            "errors": errors,
            "critical_errors": errors,
            "validation_result": enterprise_validation,
        })
        if not errors:
            remaining_failed_rules = set()

        validation_score = round(float(rule_result.get("score") or 0) * 100)
        validation = {
            **previous_validation,
            "valid": len(errors) == 0,
            "mode": "PARTIAL_RETRY",
            "score": rule_result.get("score", 0),
            "validation_score": validation_score,
            "errors": errors,
            "critical_errors": errors,
            "non_critical_errors": [],
            "required_field_errors": [error for error in errors if "Missing required field" in error],
            "components": rule_result.get("components", {}),
            "weights": rule_result.get("weights", {}),
            "failed_rules": sorted(remaining_failed_rules),
            "validation_result": {
                **enterprise_validation,
                "failed_rules": sorted(remaining_failed_rules),
            },
            "explanation": ["Partial retry re-ran failed validation rules only"],
        }
        return validation

    def _store_suggestions(self, claim_id: str, suggestions: List[Dict[str, Any]]):
        if not self.db:
            return
        for suggestion in suggestions:
            self.db.add(AISuggestion(
                claim_id=claim_id,
                field=suggestion.get("field"),
                current_value=suggestion.get("current"),
                suggested_value=suggestion.get("suggested"),
                confidence=float(suggestion.get("confidence") or 0),
                reason=suggestion.get("reason"),
            ))
        self.db.commit()

    def _store_corrections(self, claim_id: str, corrections: List[Dict[str, Any]]):
        if not self.db:
            return
        for correction in corrections:
            self.db.add(CorrectionHistory(
                claim_id=claim_id,
                field=correction.get("field"),
                previous_value=correction.get("previous"),
                corrected_value=correction.get("corrected"),
                confidence=float(correction.get("confidence") or 0),
                source=correction.get("source", "AUTO_CORRECT"),
            ))
        self.db.commit()

    def _store_repair_log(self, claim_id: str, status: str, retry_count: int, state: Dict[str, Any]):
        if not self.db:
            return
        corrections = state.get("correction_history") or []
        confidence = 0.0
        if corrections:
            confidence = sum(float(item.get("confidence") or 0) for item in corrections) / len(corrections)
        self.db.add(RepairLog(
            claim_id=claim_id,
            status=status,
            retry_count=retry_count,
            confidence_score=confidence,
            details={
                "validation": state.get("validation"),
                "corrections": corrections,
                "suggestions": state.get("ai_suggestions", []),
            },
        ))
        self.db.commit()

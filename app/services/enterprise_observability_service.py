from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.case_management.models.case_models import Case, CaseAuditLog
from app.db.database import SessionLocal
from app.models.ai_repair_model import ExtractionConfidence, TextractEntity
from app.models.claim_model import Claim
from app.models.compliance_audit_model import ComplianceAudit
from app.models.enterprise_observability_model import (
    AgentEventRecord,
    ClaimMetric,
    DecisionLog,
    PayerRule,
)
from app.models.pipeline_events_model import PipelineEvent


CONFIDENCE_THRESHOLD = 0.75
MANDATORY_FIELDS = {
    "patient.name": "Patient name",
    "patient.dob": "Patient DOB",
    "payer.name": "Payer name",
    "member_id": "Member ID",
    "provider.npi": "Provider NPI",
    "services": "Services",
}


def utcnow() -> datetime:
    return datetime.utcnow()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def claim_payload(claim: Claim | Dict[str, Any] | None) -> Dict[str, Any]:
    if claim is None:
        return {}
    if isinstance(claim, dict):
        return claim.get("claim", claim) if isinstance(claim.get("claim"), dict) else claim
    payload = _as_dict(getattr(claim, "payload", None))
    data = dict(payload.get("claim", payload)) if isinstance(payload.get("claim"), dict) else dict(payload)
    if getattr(claim, "form_type", None) and not data.get("form_type"):
        data["form_type"] = getattr(claim, "form_type")
    if getattr(claim, "ocr_text", None) and not data.get("ocr_text"):
        data["ocr_text"] = getattr(claim, "ocr_text")
    if getattr(claim, "extraction_summary", None) and not data.get("extraction_summary"):
        data["extraction_summary"] = getattr(claim, "extraction_summary")
    return data


def full_payload(claim: Claim | Dict[str, Any] | None) -> Dict[str, Any]:
    if claim is None:
        return {}
    if isinstance(claim, dict):
        return claim
    payload = dict(_as_dict(getattr(claim, "payload", None)))
    if getattr(claim, "form_type", None) and not payload.get("form_type"):
        payload["form_type"] = getattr(claim, "form_type")
    if getattr(claim, "ocr_text", None) and not payload.get("ocr_text"):
        payload["ocr_text"] = getattr(claim, "ocr_text")
    if getattr(claim, "extraction_summary", None) and not payload.get("extraction_summary"):
        payload["extraction_summary"] = getattr(claim, "extraction_summary")
    return payload


def _dig(data: Any, path: str) -> Any:
    cursor = data
    for part in path.split("."):
        if isinstance(cursor, dict):
            cursor = cursor.get(part)
        elif isinstance(cursor, list) and part.isdigit():
            index = int(part)
            cursor = cursor[index] if index < len(cursor) else None
        else:
            return None
    return cursor


def _deep_find(data: Any, names: Iterable[str]) -> Any:
    wanted = {name.lower() for name in names}
    queue = [data]
    seen = 0
    while queue and seen < 5000:
        current = queue.pop(0)
        seen += 1
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() in wanted and value not in (None, "", [], {}):
                    return value
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(item for item in current if isinstance(item, (dict, list)))
    return None


def _first_value(data: Any, *paths_or_keys: str) -> Any:
    for key in paths_or_keys:
        value = _dig(data, key) if "." in key else _as_dict(data).get(key)
        if value not in (None, "", [], {}):
            return value
    return _deep_find(data, paths_or_keys)


def _listify(value: Any) -> List[Any]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _string_list(value: Any) -> List[str]:
    items: List[str] = []
    for item in _listify(value):
        if isinstance(item, dict):
            for key in ("code", "cpt", "hcpcs", "icd", "diagnosis_code", "name", "drug"):
                if item.get(key):
                    items.append(str(item[key]))
                    break
        else:
            items.extend(part.strip() for part in re.split(r"[,;|]", str(item)) if part.strip())
    return [item for item in items if item]


def _count_items(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1


def normalize_confidence(value: Any) -> Optional[float]:
    if value in (None, "", [], {}):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, number))


def confidence_percent(value: Any) -> Optional[int]:
    normalized = normalize_confidence(value)
    return None if normalized is None else round(normalized * 100)


def parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value / 1000 if value > 10_000_000_000 else value)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _duration_ms(start: Any, end: Any) -> Optional[float]:
    started = parse_datetime(start)
    finished = parse_datetime(end)
    if not started or not finished:
        return None
    return max(0.0, (finished - started).total_seconds() * 1000)


def _payer_name(data: Dict[str, Any]) -> str:
    payer = data.get("payer")
    if isinstance(payer, dict):
        return str(payer.get("name") or payer.get("payer_name") or payer.get("id") or "").strip()
    return str(payer or data.get("payer_name") or data.get("insurance_payer") or "").strip()


def _member_id(data: Dict[str, Any]) -> Any:
    return (
        _first_value(data, "member_id", "subscriber_id", "policy_number", "insurance.member_id", "patient.member_id")
        or _dig(data, "payer.member_id")
        or _dig(data, "payer.subscriber_id")
    )


def _service_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    services = _first_value(data, "services", "service_lines", "claim.services")
    if isinstance(services, list):
        return [service for service in services if isinstance(service, dict)]
    return []


def cpt_codes(data: Dict[str, Any]) -> List[str]:
    values = _string_list(_first_value(data, "cpt_codes", "cpts", "procedure_codes"))
    values.extend(str(service.get("cpt") or service.get("hcpcs") or "").strip() for service in _service_list(data))
    return [value for value in values if value]


def icd_codes(data: Dict[str, Any]) -> List[str]:
    values = _string_list(_first_value(data, "icd_codes", "diagnosis_codes", "diagnoses", "diagnosis"))
    return [value for value in values if value]


def drug_names(data: Dict[str, Any]) -> List[str]:
    return _string_list(_first_value(data, "drugs", "drug", "medications", "medication", "ndc_codes", "ndc"))


def detect_form_type_from_payload(data: Dict[str, Any], ocr_text: str = "") -> str:
    explicit = _first_value(data, "form_type", "claim_type", "detected_form", "form_detection.form_type")
    if explicit:
        normalized = str(explicit).upper().replace("-", "").replace("_", "").replace(" ", "")
        if normalized in {"CMS1500", "CMS1450"}:
            return "CMS1500" if normalized == "CMS1500" else "UB04"
        if normalized in {"UB04", "UB92"}:
            return "UB04"
        if "REIMBURSE" in normalized:
            return "Reimbursement"
        if "AUTH" in normalized or "PA" == normalized:
            return "Prior Authorization"
        if "CUSTOM" in normalized:
            return "Custom"
        return str(explicit)

    text = f"{ocr_text} {json.dumps(data, default=str)[:15000]}".lower()
    if "cms-1500" in text or "cms1500" in text or "health insurance claim form" in text:
        return "CMS1500"
    if "ub-04" in text or "ub04" in text or "cms-1450" in text:
        return "UB04"
    if "prior authorization" in text or "preauthorization" in text:
        return "Prior Authorization"
    if "reimbursement" in text or "expense reimbursement" in text:
        return "Reimbursement"
    return "Custom"


def extract_ocr_text(claim: Claim | Dict[str, Any], db: Optional[Session] = None) -> str:
    payload = full_payload(claim)
    data = claim_payload(claim)
    direct = _first_value(
        payload,
        "ocr_text",
        "extracted_text",
        "textract_text",
        "raw_text",
        "text",
        "extraction.text",
        "document.text",
        "ocr.text",
    ) or _first_value(data, "ocr_text", "extracted_text", "textract_text", "raw_text", "text")
    if direct:
        if isinstance(direct, list):
            return "\n".join(str(item) for item in direct if item)
        return str(direct)

    blocks = _first_value(payload, "lines", "ocr_lines", "textract.lines", "document.lines")
    if isinstance(blocks, list):
        line_text = "\n".join(str(item.get("text") if isinstance(item, dict) else item) for item in blocks if item)
        if line_text.strip():
            return line_text

    claim_id = _first_value(data, "claim_id") or getattr(claim, "claim_id", None)
    if db and claim_id:
        rows = (
            db.query(TextractEntity)
            .filter(TextractEntity.claim_id == str(claim_id))
            .order_by(TextractEntity.page.asc(), TextractEntity.id.asc())
            .all()
        )
        text = "\n".join(row.text for row in rows if row.text)
        if text.strip():
            return text
    return ""


def missing_required_fields(data: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for path, label in MANDATORY_FIELDS.items():
        if path == "member_id":
            value = _member_id(data)
        else:
            value = _dig(data, path) if "." in path else data.get(path)
        if value in (None, "", [], {}):
            missing.append(label)
    if not cpt_codes(data):
        missing.append("CPT codes")
    if not icd_codes(data):
        missing.append("ICD codes")
    return missing


def payer_validation_failed(data: Dict[str, Any]) -> bool:
    validation = _first_value(data, "payer_validation", "coverage", "eligibility", "validation")
    if isinstance(validation, dict):
        status = str(validation.get("status") or validation.get("coverage_status") or validation.get("eligible") or "").upper()
        if status in {"FAILED", "INVALID", "INACTIVE", "DENIED", "FALSE", "NOT_ELIGIBLE"}:
            return True
        if validation.get("valid") is False or validation.get("eligible") is False:
            return True
    return bool(_first_value(data, "coverage_mismatch", "payer_validation_failed"))


def hitl_reasons_for_claim(claim: Claim | Dict[str, Any], validation_result: Optional[Dict[str, Any]] = None, db: Optional[Session] = None) -> List[str]:
    data = claim_payload(claim)
    payload = full_payload(claim)
    extraction = _as_dict(_first_value(payload, "extraction", "extraction_summary")) or _as_dict(data.get("extraction"))
    confidence = normalize_confidence(
        _first_value(extraction, "confidence_score", "confidence", "extraction_confidence", "ocr_confidence")
        or _first_value(data, "confidence_score", "confidence", "ai_confidence")
    )
    if confidence is None and db and getattr(claim, "claim_id", None):
        confidence = normalize_confidence(
            db.query(func.avg(ExtractionConfidence.confidence))
            .filter(ExtractionConfidence.claim_id == claim.claim_id)
            .scalar()
        )

    reasons: List[str] = []
    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        reasons.append("Low confidence")
    reasons.extend(f"Missing {field}" for field in missing_required_fields(data))
    if payer_validation_failed(data):
        reasons.append("Coverage mismatch")
    if validation_result and validation_result.get("drug_match") is False:
        reasons.append("Drug mismatch")
    if data.get("drug_mismatch") or _first_value(data, "drug_mismatch"):
        reasons.append("Drug mismatch")
    return list(dict.fromkeys(reasons))


def build_extraction_summary(claim: Claim, db: Session) -> Dict[str, Any]:
    payload = full_payload(claim)
    data = claim_payload(claim)
    extraction = _as_dict(_first_value(payload, "extraction", "extraction_summary")) or _as_dict(data.get("extraction"))
    field_confidence = _first_value(payload, "field_confidence", "field_confidences") or _first_value(data, "field_confidence")
    db_confidence = None
    db_field_count = 0
    if getattr(claim, "claim_id", None):
        db_confidence = (
            db.query(func.avg(ExtractionConfidence.confidence))
            .filter(ExtractionConfidence.claim_id == claim.claim_id)
            .scalar()
        )
        db_field_count = (
            db.query(ExtractionConfidence)
            .filter(ExtractionConfidence.claim_id == claim.claim_id)
            .count()
        )

    confidence = normalize_confidence(
        _first_value(extraction, "confidence_score", "confidence", "extraction_confidence", "ocr_confidence")
        or _first_value(data, "confidence_score", "confidence", "ai_confidence")
        or db_confidence
    )
    if confidence is None and isinstance(field_confidence, list) and field_confidence:
        scores = [
            normalize_confidence(item.get("confidence") if isinstance(item, dict) else item)
            for item in field_confidence
        ]
        scores = [score for score in scores if score is not None]
        confidence = sum(scores) / len(scores) if scores else None

    fields = (
        _first_value(extraction, "fields", "extracted_fields", "mapped_fields")
        or _first_value(data, "fields", "extracted_fields", "mapped_fields")
        or _as_dict(data)
    )
    services = _service_list(data)
    processing_duration = (
        _first_value(extraction, "processing_duration", "duration", "processing_time")
        or _first_value(payload, "processing_duration", "duration", "processing_time")
        or _sum_stage_history_duration(payload)
    )
    ocr_text = extract_ocr_text(claim, db)
    form_type = detect_form_type_from_payload(data, ocr_text)
    validation_result = _as_dict(_first_value(payload, "validation.validation_result", "validation_result"))
    reasons = hitl_reasons_for_claim(claim, validation_result=validation_result, db=db)
    status = "SUCCESS"
    if reasons:
        status = "REVIEW_REQUIRED"
    if confidence is None and not _count_items(fields):
        status = "PENDING"

    uploaded_file = (
        _first_value(payload, "uploaded_file", "file_name", "filename", "document_name", "s3_key", "file")
        or _first_value(data, "uploaded_file", "file_name", "filename", "document_name", "s3_key", "file")
    )

    return {
        "claim_id": claim.claim_id,
        "uploaded_file": uploaded_file,
        "detected_form_type": form_type,
        "form_type": form_type,
        "confidence_score": round(confidence, 4) if confidence is not None else None,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "extraction_status": status,
        "hitl_required": bool(reasons),
        "hitl_reason": reasons,
        "ocr_confidence": round(confidence * 100, 2) if confidence is not None else None,
        "extracted_field_count": max(_count_items(fields), db_field_count),
        "extracted_services_count": len(services),
        "processing_duration": processing_duration,
    }


def _sum_stage_history_duration(payload: Dict[str, Any]) -> Optional[float]:
    history = _first_value(payload, "stage_history", "claim.stage_history", "pipeline.stage_history")
    if not isinstance(history, list):
        return None
    total = 0.0
    for item in history:
        if not isinstance(item, dict):
            continue
        value = item.get("duration_ms") or item.get("duration") or item.get("duration_seconds")
        try:
            value = float(value or 0)
        except (TypeError, ValueError):
            continue
        total += value if value > 100 else value * 1000
    return round(total, 2) if total else None


def _valid_cpt(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{4,5}", str(code).strip().upper()))


def _valid_icd(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][0-9][0-9A-Z](?:\.?[0-9A-Z]{0,4})?", str(code).strip().upper()))


def _rule_matches(condition: Dict[str, Any], data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    details: List[str] = []
    if not condition:
        return True, details

    for field in _listify(condition.get("required_fields")):
        if _dig(data, str(field)) in (None, "", [], {}):
            return False, [f"Missing payer-required field {field}"]

    field = condition.get("field")
    if field:
        actual = _dig(data, str(field)) or _first_value(data, str(field))
        expected = condition.get("value")
        operator = str(condition.get("operator") or condition.get("op") or "equals").lower()
        if operator in {"exists", "required"}:
            passed = actual not in (None, "", [], {})
        elif operator in {"equals", "eq"}:
            passed = str(actual).lower() == str(expected).lower()
        elif operator in {"not_equals", "ne"}:
            passed = str(actual).lower() != str(expected).lower()
        elif operator == "contains":
            passed = str(expected).lower() in str(actual or "").lower()
        elif operator == "in":
            passed = str(actual).lower() in {str(item).lower() for item in _listify(expected)}
        elif operator in {"min", "gte"}:
            passed = float(actual or 0) >= float(expected or 0)
        elif operator in {"max", "lte"}:
            passed = float(actual or 0) <= float(expected or 0)
        else:
            passed = True
        if not passed:
            return False, [f"{field} failed payer rule condition"]

    for code in _string_list(condition.get("cpt_codes") or condition.get("cpt")):
        if code and code not in cpt_codes(data):
            return False, [f"CPT {code} required by payer rule"]

    for code in _string_list(condition.get("icd_codes") or condition.get("icd")):
        if code and code not in icd_codes(data):
            return False, [f"ICD {code} required by payer rule"]

    return True, details


def evaluate_payer_rules(db: Session, data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], List[str], bool, bool]:
    payer = _payer_name(data)
    rules = (
        db.query(PayerRule)
        .filter((func.lower(PayerRule.payer_name) == payer.lower()) | (func.lower(PayerRule.payer_name) == "global"))
        .order_by(PayerRule.created_at.asc())
        .all()
        if payer
        else db.query(PayerRule).filter(func.lower(PayerRule.payer_name) == "global").all()
    )
    evaluated: List[Dict[str, Any]] = []
    warnings: List[str] = []
    explanations: List[str] = []
    coverage_valid = True
    drug_match = True

    for rule in rules:
        condition = _as_dict(rule.condition)
        action = _as_dict(rule.action)
        passed, details = _rule_matches(condition, data)
        evaluated.append({
            "id": rule.id,
            "payer_name": rule.payer_name,
            "rule_name": rule.rule_name,
            "rule_type": rule.rule_type,
            "passed": passed,
            "details": details,
        })
        if passed:
            continue

        message = action.get("message") or action.get("warning") or action.get("explanation") or "; ".join(details) or rule.rule_name
        if message:
            warnings.append(str(message))
            explanations.append(str(action.get("explanation") or message))
        rule_type = str(rule.rule_type or "").lower()
        if "coverage" in rule_type or action.get("coverage_valid") is False:
            coverage_valid = False
        if "drug" in rule_type or action.get("drug_match") is False:
            drug_match = False

    return evaluated, warnings, explanations, coverage_valid, drug_match


def validate_claim_enterprise(claim: Claim | Dict[str, Any], db: Session) -> Dict[str, Any]:
    data = claim_payload(claim)
    cpts = cpt_codes(data)
    icds = icd_codes(data)
    drugs = drug_names(data)
    missing = missing_required_fields(data)
    cpt_valid = bool(cpts) and all(_valid_cpt(code) for code in cpts)
    icd_valid = bool(icds) and all(_valid_icd(code) for code in icds)
    drug_match = True
    explanations: List[str] = []
    warnings: List[str] = []

    if drugs and not icds:
        drug_match = False
        warnings.append("Drug mismatch")
        explanations.append("Drug validation requires at least one diagnosis code")

    coverage_valid = not payer_validation_failed(data)
    if not coverage_valid:
        warnings.append("Coverage mismatch")
        explanations.append("Payer coverage or eligibility validation failed")

    evaluated_rules, rule_warnings, rule_explanations, rule_coverage_valid, rule_drug_match = evaluate_payer_rules(db, data)
    warnings.extend(rule_warnings)
    explanations.extend(rule_explanations)
    coverage_valid = coverage_valid and rule_coverage_valid
    drug_match = drug_match and rule_drug_match

    if not cpt_valid:
        warnings.append("Invalid or missing CPT")
        explanations.append("CPT validation failed for one or more service lines")
    if not icd_valid:
        warnings.append("Invalid or missing ICD")
        explanations.append("ICD diagnosis validation failed")
    if missing:
        explanations.append(f"Mandatory field validation failed: {', '.join(missing)}")

    return {
        "cpt_valid": cpt_valid,
        "icd_valid": icd_valid,
        "drug_match": drug_match,
        "coverage_valid": coverage_valid,
        "missing_fields": missing,
        "warnings": list(dict.fromkeys(warnings)),
        "explanation": list(dict.fromkeys(explanations)),
        "rules_evaluated": evaluated_rules,
    }


def route_case_for_claim(claim: Claim | Dict[str, Any], validation_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = claim_payload(claim)
    payload = full_payload(claim)
    risk = _first_value(data, "denial_risk.risk_score", "risk_score", "denial_score")
    confidence = normalize_confidence(
        _first_value(data, "confidence", "confidence_score", "ai_confidence")
        or _first_value(payload, "extraction.confidence_score", "extraction.extraction_confidence")
    )
    try:
        risk_value = float(risk or 0)
    except (TypeError, ValueError):
        risk_value = 0
    if 0 < risk_value <= 1:
        risk_value *= 100

    legal_issue = bool(_first_value(data, "legal_issue", "legal_hold", "compliance.legal_issue"))
    if legal_issue:
        assigned_team = "Legal Team"
        priority = "HIGH"
        next_stage = "LEGAL_REVIEW"
        escalation_level = 2
        reason = "Legal issue detected"
    elif risk_value > 80:
        assigned_team = "Compliance Team"
        priority = "HIGH"
        next_stage = "COMPLIANCE_REVIEW"
        escalation_level = 1
        reason = "Denial risk exceeds 80%"
    elif confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        assigned_team = "MA Team"
        priority = "HIGH"
        next_stage = "HUMAN_REVIEW"
        escalation_level = 0
        reason = "Extraction confidence below threshold"
    elif validation_result and (validation_result.get("coverage_valid") is False or validation_result.get("drug_match") is False):
        assigned_team = "HEOR Team"
        priority = "HIGH"
        next_stage = "PAYER_REVIEW"
        escalation_level = 0
        reason = "Clinical or payer validation requires review"
    else:
        assigned_team = "MA Team"
        priority = "MEDIUM"
        next_stage = "STANDARD_REVIEW"
        escalation_level = 0
        reason = "Standard claim review"

    sla_hours = 2 if priority == "HIGH" else 4
    return {
        "assigned_team": assigned_team,
        "assigned_role": assigned_team,
        "priority": priority,
        "next_stage": next_stage,
        "escalation_level": escalation_level,
        "sla_deadline": (utcnow() + timedelta(hours=sla_hours)).isoformat(),
        "routing_reason": reason,
        "risk_score": round(risk_value, 2),
        "confidence": round(confidence * 100, 2) if confidence is not None else None,
    }


def log_decision(
    db: Session,
    claim_id: str,
    agent: str,
    input_payload: Dict[str, Any],
    rules_evaluated: Any,
    decision: str,
    reasoning: str,
) -> DecisionLog:
    row = DecisionLog(
        claim_id=claim_id,
        agent=agent,
        input_payload=_jsonable(input_payload or {}),
        rules_evaluated=_jsonable(rules_evaluated or []),
        decision=decision,
        reasoning=reasoning,
    )
    db.add(row)
    db.flush()
    return row


def log_decision_safe(claim_id: str, agent: str, input_payload: Dict[str, Any], rules_evaluated: Any, decision: str, reasoning: str) -> None:
    db = SessionLocal()
    try:
        log_decision(db, claim_id, agent, input_payload, rules_evaluated, decision, reasoning)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _event_datetime(payload: Dict[str, Any], *keys: str) -> Optional[datetime]:
    for key in keys:
        value = _first_value(payload, key)
        parsed = parse_datetime(value)
        if parsed:
            return parsed
    return None


def persist_agent_event(payload: Dict[str, Any]) -> None:
    claim_id = _first_value(payload, "claim_id", "claimId")
    details = _as_dict(payload.get("details"))
    start_time = _event_datetime(payload, "start_time", "started_at", "startedAt") or parse_datetime(payload.get("timestamp"))
    end_time = _event_datetime(payload, "end_time", "completed_at", "completedAt")
    duration = _first_value(payload, "duration", "processing_time", "processingTime")
    if duration in (None, ""):
        duration = _duration_ms(start_time, end_time)
    try:
        duration_number = float(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration_number = None
    input_payload = _first_value(payload, "input", "input_data", "inputData")
    output_payload = _first_value(payload, "output", "output_data", "outputData", "result")
    db = SessionLocal()
    try:
        db.add(AgentEventRecord(
            claim_id=str(claim_id) if claim_id else None,
            agent=str(_first_value(payload, "agent", "current_agent", "step") or "Pipeline"),
            stage=str(_first_value(payload, "stage", "current_stage", "active_step", "step") or ""),
            status=str(_first_value(payload, "status") or "INFO").upper(),
            progress=float(_first_value(payload, "progress") or 0) if _first_value(payload, "progress") not in (None, "") else None,
            start_time=start_time,
            end_time=end_time,
            duration=duration_number,
            input_count=int(_first_value(payload, "input_count") or _count_items(input_payload) or 0),
            output_count=int(_first_value(payload, "output_count") or _count_items(output_payload) or 0),
            details=_jsonable({key: value for key, value in payload.items() if key not in {"type", "event"}}),
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def serialize_agent_event(row: AgentEventRecord) -> Dict[str, Any]:
    return {
        "id": row.id,
        "claim_id": row.claim_id,
        "agent": row.agent,
        "stage": row.stage,
        "status": row.status,
        "progress": row.progress,
        "start_time": row.start_time.isoformat() if row.start_time else None,
        "end_time": row.end_time.isoformat() if row.end_time else None,
        "duration": row.duration,
        "input_count": row.input_count,
        "output_count": row.output_count,
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def audit_evidence_for_claim(claim_id: str, db: Session) -> Dict[str, Any]:
    decisions = (
        db.query(DecisionLog)
        .filter(DecisionLog.claim_id == claim_id)
        .order_by(DecisionLog.timestamp.asc())
        .all()
    )
    agent_events = (
        db.query(AgentEventRecord)
        .filter(AgentEventRecord.claim_id == claim_id)
        .order_by(AgentEventRecord.created_at.asc())
        .all()
    )
    pipeline_events = (
        db.query(PipelineEvent)
        .filter(PipelineEvent.claim_id == claim_id)
        .order_by(PipelineEvent.timestamp.asc())
        .all()
    )
    compliance = (
        db.query(ComplianceAudit)
        .filter(ComplianceAudit.claim_id == claim_id)
        .order_by(ComplianceAudit.timestamp.asc())
        .all()
    )
    case_ids = [case.case_id for case in db.query(Case).filter(Case.claim_id == claim_id).all()]
    case_audits = (
        db.query(CaseAuditLog)
        .filter(CaseAuditLog.case_id.in_(case_ids))
        .order_by(CaseAuditLog.created_at.asc())
        .all()
        if case_ids
        else []
    )

    timeline = []
    for row in decisions:
        timeline.append({
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "event": f"{row.agent} decision",
            "detail": row.reasoning or row.decision,
            "source": "decision_logs",
        })
    for row in agent_events:
        timeline.append({
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "event": f"{row.agent} {row.status}",
            "detail": _as_dict(row.details).get("message") or row.stage,
            "source": "agent_events",
        })
    for row in pipeline_events:
        timeline.append({
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "event": f"{row.agent or 'Pipeline'} {row.status or ''}".strip(),
            "detail": row.message,
            "source": "pipeline_events",
        })
    for row in compliance:
        timeline.append({
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "event": f"Compliance {row.status}",
            "detail": json.dumps(row.issues or row.audit_details or {}, default=str),
            "source": "compliance_audit",
        })
    for row in case_audits:
        timeline.append({
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "event": row.action,
            "detail": json.dumps(row.details or {}, default=str),
            "source": "case_audit_logs",
        })
    timeline.sort(key=lambda item: item.get("timestamp") or "")

    return {
        "claim_id": claim_id,
        "timeline": timeline,
        "decision_logs": [
            {
                "id": row.id,
                "agent": row.agent,
                "input_payload": row.input_payload,
                "rules_evaluated": row.rules_evaluated,
                "decision": row.decision,
                "reasoning": row.reasoning,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in decisions
        ],
        "agent_events": [serialize_agent_event(row) for row in agent_events],
        "compliance": [
            {
                "id": row.id,
                "status": row.status,
                "issues": row.issues,
                "audit_details": row.audit_details,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in compliance
        ],
    }


def export_evidence(evidence: Dict[str, Any], file_format: str) -> Tuple[bytes, str]:
    fmt = file_format.lower()
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["timestamp", "event", "detail", "source"])
        writer.writeheader()
        for row in evidence.get("timeline", []):
            writer.writerow({
                "timestamp": row.get("timestamp") or "",
                "event": row.get("event") or "",
                "detail": row.get("detail") or "",
                "source": row.get("source") or "",
            })
        return buffer.getvalue().encode("utf-8"), "text/csv"
    if fmt == "pdf":
        lines = [f"Evidence Export: {evidence.get('claim_id', '')}"]
        for row in evidence.get("timeline", [])[:120]:
            lines.append(f"{row.get('timestamp', '')} {row.get('event', '')} {row.get('detail', '')}")
        stream = "BT /F1 10 Tf 40 760 Td (" + "\\n".join(lines).replace("(", "[").replace(")", "]")[:3500] + ") Tj ET"
        pdf = (
            "%PDF-1.4\n"
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
            "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            f"5 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
            "xref\n0 6\n0000000000 65535 f \ntrailer << /Root 1 0 R /Size 6 >>\nstartxref\n0\n%%EOF\n"
        )
        return pdf.encode("latin-1", errors="ignore"), "application/pdf"
    return json.dumps(evidence, indent=2, default=str).encode("utf-8"), "application/json"


def _claim_amount(data: Dict[str, Any]) -> float:
    value = _first_value(data, "paid_amount", "payment.paid_amount", "payment.amount", "amount", "total_charge", "charge")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _claim_status(claim: Claim, data: Dict[str, Any]) -> str:
    return str(getattr(claim, "status", None) or data.get("status") or "").upper()


def enterprise_analytics(db: Session) -> Dict[str, Any]:
    claims = db.query(Claim).order_by(Claim.created_at.asc()).all()
    cases = db.query(Case).all()
    agent_rows = db.query(AgentEventRecord).order_by(AgentEventRecord.created_at.desc()).limit(2000).all()
    decision_rows = db.query(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(2000).all()
    metric_rows = db.query(ClaimMetric).order_by(ClaimMetric.created_at.desc()).limit(2000).all()

    cycle_times: List[float] = []
    payment_times: List[float] = []
    payer_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"payer": "Unknown", "total": 0, "success": 0, "denied": 0, "revenue": 0.0, "cycle_ms": []})
    denial_counter: Counter[str] = Counter()
    trend_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"period": "", "claims": 0, "revenue": 0.0, "denials": 0, "success": 0})
    success = 0

    for claim in claims:
        data = claim_payload(claim)
        payload = full_payload(claim)
        status = _claim_status(claim, data)
        created_at = getattr(claim, "created_at", None)
        updated_at = parse_datetime(_first_value(payload, "finalized_at", "completed_at", "paid_at")) or getattr(claim, "updated_at", None)
        if created_at and updated_at:
            ms = max(0.0, (updated_at - created_at).total_seconds() * 1000)
            if ms:
                cycle_times.append(ms)
        paid_at = parse_datetime(_first_value(payload, "payment.paid_at", "paid_at", "payment.completed_at"))
        if created_at and paid_at:
            payment_times.append(max(0.0, (paid_at - created_at).total_seconds() * 1000))
        payer = _payer_name(data) or "Unknown"
        stats = payer_stats[payer]
        stats["payer"] = payer
        stats["total"] += 1
        stats["revenue"] += _claim_amount(data)
        if created_at and updated_at:
            stats["cycle_ms"].append(max(0.0, (updated_at - created_at).total_seconds() * 1000))
        if status in {"PAID", "APPROVED", "COMPLETED", "SUCCESS", "ACCEPTED"}:
            stats["success"] += 1
            success += 1
        if status in {"DENIED", "REJECTED", "FAILED", "HITL_REQUIRED"}:
            stats["denied"] += 1
            reason = (
                _first_value(data, "denial_reason", "rejection_reason", "denial.reason", "denial_ai.denial_reason", "denial_ai.root_cause")
                or "Unspecified"
            )
            denial_counter[str(reason)] += 1
        if created_at:
            period = created_at.strftime("%Y-%m-%d")
            trend = trend_map[period]
            trend["period"] = period
            trend["claims"] += 1
            trend["revenue"] += _claim_amount(data)
            trend["denials"] += 1 if status in {"DENIED", "REJECTED", "FAILED"} else 0
            trend["success"] += 1 if status in {"PAID", "APPROVED", "COMPLETED", "SUCCESS", "ACCEPTED"} else 0

    payer_ranking = []
    for stats in payer_stats.values():
        total = stats["total"] or 1
        avg_cycle = sum(stats["cycle_ms"]) / len(stats["cycle_ms"]) if stats["cycle_ms"] else 0
        payer_ranking.append({
            "payer": stats["payer"],
            "total": stats["total"],
            "success": stats["success"],
            "denied": stats["denied"],
            "success_rate": round((stats["success"] / total) * 100, 2),
            "denial_rate": round((stats["denied"] / total) * 100, 2),
            "revenue": round(stats["revenue"], 2),
            "avg_cycle_ms": round(avg_cycle, 2),
        })
    payer_ranking.sort(key=lambda item: (item["success_rate"], item["total"]), reverse=True)
    best_payer = payer_ranking[0]["payer"] if payer_ranking else None
    worst_payer = sorted(payer_ranking, key=lambda item: (item["denial_rate"], item["total"]), reverse=True)[0]["payer"] if payer_ranking else None

    now = utcnow()
    open_cases = [case for case in cases if str(case.status).upper() not in {"CLOSED", "APPROVED", "REJECTED"}]
    compliant_cases = [
        case for case in cases
        if not case.sla_due_at or case.sla_due_at >= now or str(case.status).upper() in {"CLOSED", "APPROVED", "REJECTED"}
    ]
    sla_compliance = round((len(compliant_cases) / len(cases)) * 100, 2) if cases else 0

    agent_group: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"agent": "", "events": 0, "completed": 0, "failed": 0, "duration_ms": []})
    for row in agent_rows:
        group = agent_group[row.agent]
        group["agent"] = row.agent
        group["events"] += 1
        status = str(row.status or "").upper()
        if status in {"COMPLETED", "SUCCESS", "DONE", "ACCEPTED"}:
            group["completed"] += 1
        if status in {"FAILED", "ERROR", "DENIED", "REJECTED"}:
            group["failed"] += 1
        if row.duration:
            group["duration_ms"].append(float(row.duration))

    agent_performance = []
    for group in agent_group.values():
        durations = group["duration_ms"]
        agent_performance.append({
            "agent": group["agent"],
            "events": group["events"],
            "completed": group["completed"],
            "failed": group["failed"],
            "failure_rate": round((group["failed"] / max(group["events"], 1)) * 100, 2),
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
        })
    agent_performance.sort(key=lambda item: item["events"], reverse=True)

    avg_cycle = sum(cycle_times) / len(cycle_times) if cycle_times else 0
    avg_payment = sum(payment_times) / len(payment_times) if payment_times else 0
    total_claims = len(claims)
    claim_success_ratio = round((success / total_claims) * 100, 2) if total_claims else 0
    top_denial_reason = denial_counter.most_common(1)[0][0] if denial_counter else None

    return {
        "summary": {
            "total_claims": total_claims,
            "average_processing_time_ms": round(avg_cycle, 2),
            "average_payment_time_ms": round(avg_payment, 2),
            "top_denial_reason": top_denial_reason,
            "best_payer": best_payer,
            "worst_payer": worst_payer,
            "sla_compliance": sla_compliance,
            "claim_success_ratio": claim_success_ratio,
            "open_cases": len(open_cases),
            "decision_log_count": len(decision_rows),
            "metric_count": len(metric_rows),
        },
        "claim_trends": list(sorted(trend_map.values(), key=lambda item: item["period"])),
        "payer_ranking": payer_ranking,
        "denial_reasons": [{"reason": reason, "count": count} for reason, count in denial_counter.most_common()],
        "agent_performance": agent_performance,
        "cycle_time": {
            "average_ms": round(avg_cycle, 2),
            "samples": len(cycle_times),
        },
        "sla_metrics": {
            "compliance": sla_compliance,
            "open_cases": len(open_cases),
            "total_cases": len(cases),
        },
    }

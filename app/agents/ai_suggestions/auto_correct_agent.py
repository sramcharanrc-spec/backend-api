import copy
import re
from datetime import datetime
from typing import Any, Dict, List

from app.websocket.manager import manager


def _set_path(data: Dict[str, Any], path: str, value: Any):
    parts = path.split(".")
    cursor = data
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _get_path(data: Dict[str, Any], path: str) -> Any:
    cursor: Any = data
    for part in path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def is_placeholder(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0 or any(is_placeholder(item) for item in value)
    return str(value).strip().upper() in {"9999999999", "0000000000", "UNKNOWN", ""}


def _normalize_dob(value: Any) -> Any:
    if not value:
        return value
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _normalize_icd(code: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9.]", "", str(code or "")).upper()
    if len(text) > 3 and "." not in text:
        return f"{text[:3]}.{text[3:]}"
    return text


def _normalize_cpt(code: Any) -> str:
    digits = re.sub(r"\D", "", str(code or ""))
    return digits[:5]


def validate_npi(value: Any) -> bool:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 10 or len(set(digits)) == 1:
        return False

    payload = f"80840{digits}"
    total = 0
    for index, char in enumerate(reversed(payload)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _route_to_review(claim: Dict[str, Any], reason: str):
    claim["requires_hitl"] = True
    claim["pipeline_state"] = "WAITING_FOR_REVIEW"
    claim["pipeline_status"] = "WAITING_FOR_REVIEW"
    claim["status"] = "WAITING_FOR_REVIEW"
    claim["current_stage"] = "WAITING_FOR_REVIEW"
    claim["active_step"] = "waiting_for_review"
    claim["current_agent"] = "SUBMISSION_REVIEW"
    claim["review_state"] = "PENDING_REVIEW"
    claim["queue_state"] = "HUMAN_REVIEW"
    claim["review_required"] = True
    claim["waiting_for_human"] = True
    claim["autocorrect_blocked_reason"] = reason


class AutoCorrectAgent:
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        claim = copy.deepcopy(state.get("claim", state))
        claim_id = claim.get("claim_id", "UNKNOWN")
        suggestions = state.get("ai_suggestions") or []
        history: List[Dict[str, Any]] = []

        await manager.send_event("auto_correct", {"agent": "AUTO_CORRECT", "claim_id": claim_id, "status": "running"})

        for suggestion in suggestions:
            if float(suggestion.get("confidence") or 0) < 0.65:
                continue
            field = suggestion.get("field")
            suggested = suggestion.get("suggested")
            if not field:
                continue
            previous = suggestion.get("current")
            current_value = _get_path(claim, field)
            if not _is_missing(current_value):
                continue
            if is_placeholder(suggested):
                reason = "Auto-correction requires human review; suggested value is a placeholder"
                _route_to_review(claim, reason)
                history.append({
                    "field": field,
                    "previous": previous,
                    "corrected": None,
                    "confidence": suggestion.get("confidence", 0),
                    "source": "AUTO_CORRECT",
                    "status": "blocked",
                    "reason": reason,
                })
                state["claim"] = claim
                state["correction_history"] = history
                await manager.send_event("auto_correct", {
                    "agent": "AUTO_CORRECT",
                    "claim_id": claim_id,
                    "status": "completed",
                    "corrections": history,
                    "pipeline_state": "WAITING_FOR_REVIEW",
                    "current_stage": "WAITING_FOR_REVIEW",
                    "current_agent": "SUBMISSION_REVIEW",
                    "active_step": "waiting_for_review",
                })
                return state

            if field == "cpt_codes" and isinstance(suggested, list):
                suggested = [_normalize_cpt(code) for code in suggested if _normalize_cpt(code)]
            elif field == "icd_codes" and isinstance(suggested, list):
                suggested = [_normalize_icd(code) for code in suggested if _normalize_icd(code)]
            elif field == "patient.dob":
                suggested = _normalize_dob(suggested)
            elif field == "provider.npi":
                suggested = re.sub(r"\D", "", str(suggested or ""))[:10]
                if not validate_npi(suggested):
                    reason = "Provider NPI requires human review; auto-correction rejected an invalid suggested NPI"
                    _route_to_review(claim, reason)
                    history.append({
                        "field": field,
                        "previous": previous,
                        "corrected": None,
                        "confidence": suggestion.get("confidence", 0),
                        "source": "AUTO_CORRECT",
                        "status": "blocked",
                        "reason": reason,
                    })
                    continue
            elif field == "payer.name":
                suggested = str(suggested or "UNKNOWN_PAYER").strip().upper()
            if is_placeholder(suggested):
                reason = "Auto-correction requires human review; normalized suggestion is a placeholder"
                _route_to_review(claim, reason)
                history.append({
                    "field": field,
                    "previous": previous,
                    "corrected": None,
                    "confidence": suggestion.get("confidence", 0),
                    "source": "AUTO_CORRECT",
                    "status": "blocked",
                    "reason": reason,
                })
                state["claim"] = claim
                state["correction_history"] = history
                await manager.send_event("auto_correct", {
                    "agent": "AUTO_CORRECT",
                    "claim_id": claim_id,
                    "status": "completed",
                    "corrections": history,
                    "pipeline_state": "WAITING_FOR_REVIEW",
                    "current_stage": "WAITING_FOR_REVIEW",
                    "current_agent": "SUBMISSION_REVIEW",
                    "active_step": "waiting_for_review",
                })
                return state

            _set_path(claim, field, suggested)
            history.append({
                "field": field,
                "previous": previous,
                "corrected": suggested,
                "confidence": suggestion.get("confidence", 0),
                "source": "AUTO_CORRECT",
            })

        claim["correction_history"] = [*claim.get("correction_history", []), *history]
        state["claim"] = claim
        state["correction_history"] = history

        await manager.send_event("auto_correct", {
            "agent": "AUTO_CORRECT",
            "claim_id": claim_id,
            "status": "completed",
            "corrections": history,
        })
        return state

import asyncio
import json
import time
from typing import Any, Dict, List

from app.ai.llm_service import invoke_llm
from app.services.analytics_service import update_metrics
from app.websocket.manager import manager


def _get_path(data: Dict[str, Any], path: str):
    current = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(part)

    return current


def _safe_payer_name(claim: Dict[str, Any]) -> str:
    payer = claim.get("payer")

    if isinstance(payer, dict):
        return payer.get("name") or claim.get("payer_name") or "UNKNOWN_PAYER"

    if isinstance(payer, str):
        return payer

    insurance = claim.get("insurance")

    if isinstance(insurance, dict):
        return insurance.get("payer") or insurance.get("payer_name") or "UNKNOWN_PAYER"

    return claim.get("payer_name") or "UNKNOWN_PAYER"


def _is_denial_document(claim: Dict[str, Any]) -> bool:
    document_type = str(
        claim.get("document_type")
        or claim.get("form_type")
        or claim.get("claim_type")
        or ""
    ).upper()

    status = str(
        claim.get("status")
        or claim.get("confidence_status")
        or claim.get("pipeline_status")
        or ""
    ).upper()

    denial = claim.get("denial") if isinstance(claim.get("denial"), dict) else {}

    return (
        document_type == "EOB_ERA"
        or claim.get("denial_ai_required") is True
        or claim.get("denial_required") is True
        or status == "DENIAL_AI_REQUIRED"
        or denial.get("denied") is True
        or bool(denial.get("denial_code"))
        or bool(denial.get("carc"))
        or bool(denial.get("rarc"))
    )


def make_json_safe(value: Any, seen=None):
    """
    Convert nested claim/state objects into JSON-safe data.

    This prevents:
    ValueError: Circular reference detected

    It also removes large recursive objects like pipeline/state references.
    """
    if seen is None:
        seen = set()

    value_id = id(value)

    if isinstance(value, dict):
        if value_id in seen:
            return "[Circular Reference]"

        seen.add(value_id)

        cleaned = {}

        for key, item in value.items():
            if key in {
                "pipeline",
                "state",
                "graph_state",
                "raw_state",
                "parent",
                "self",
            }:
                cleaned[key] = "[Omitted to prevent circular reference]"
            else:
                cleaned[key] = make_json_safe(item, seen)

        seen.remove(value_id)
        return cleaned

    if isinstance(value, list):
        if value_id in seen:
            return "[Circular Reference]"

        seen.add(value_id)
        cleaned = [make_json_safe(item, seen) for item in value]
        seen.remove(value_id)
        return cleaned

    if isinstance(value, tuple):
        return [make_json_safe(item, seen) for item in value]

    if isinstance(value, set):
        return [make_json_safe(item, seen) for item in value]

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


class AISuggestionAgent:
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()

        if not isinstance(state, dict):
            state = {"claim": {}}

        claim = state.get("claim", state)

        if not isinstance(claim, dict):
            claim = {}

        claim_id = claim.get("claim_id", "UNKNOWN")
        validation = state.get("validation") if isinstance(state.get("validation"), dict) else {}
        errors = validation.get("errors") or state.get("validation_errors") or []

        await self._send_event_safe(
            "ai_suggestion",
            {
                "agent": "AI_SUGGESTION",
                "claim_id": claim_id,
                "status": "running",
            },
        )

        suggestions = self._rule_based_suggestions(claim, errors)

        try:
            llm_suggestions = await asyncio.wait_for(
                self._llm_denial_suggestions(claim, errors),
                timeout=3,
            )
        except asyncio.TimeoutError:
            llm_suggestions = []
        except Exception as exc:
            llm_suggestions = [
                {
                    "field": "ai_suggestion",
                    "current": None,
                    "suggested": "AI suggestion generation failed; use rule-based suggestions.",
                    "confidence": 0.5,
                    "reason": str(exc),
                }
            ]

        suggestions.extend(llm_suggestions)

        # Deduplicate suggestions by field + reason.
        deduped = []
        seen_keys = set()

        for suggestion in suggestions:
            if not isinstance(suggestion, dict):
                continue

            key = (
                str(suggestion.get("field") or ""),
                str(suggestion.get("reason") or ""),
            )

            if key in seen_keys:
                continue

            seen_keys.add(key)
            deduped.append(suggestion)

        state["ai_suggestions"] = deduped

        await self._send_event_safe(
            "ai_suggestion",
            {
                "agent": "AI_SUGGESTION",
                "claim_id": claim_id,
                "status": "completed",
                "suggestions": deduped,
            },
        )

        try:
            update_metrics(
                event_type="ai_suggestion_completed",
                claim_id=claim_id,
                agent="AI_SUGGESTION",
                payer=_safe_payer_name(claim),
                risk_score=claim.get("risk_score", 0),
                latency=time.time() - start_time,
                status="COMPLETED",
            )
        except Exception:
            pass

        return state

    async def _send_event_safe(self, event_name: str, payload: Dict[str, Any]) -> None:
        try:
            await manager.send_event(event_name, make_json_safe(payload))
        except TypeError:
            # Some manager implementations use send_event(channel, action, payload).
            try:
                await manager.send_event(
                    event_name,
                    str(payload.get("status") or "updated"),
                    make_json_safe(payload),
                )
            except Exception:
                pass
        except Exception:
            pass

    def _rule_based_suggestions(
        self,
        claim: Dict[str, Any],
        errors: List[Any],
    ) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []

        denial = claim.get("denial") if isinstance(claim.get("denial"), dict) else {}

        if _is_denial_document(claim):
            denial_code = denial.get("denial_code") or denial.get("carc") or "UNKNOWN"
            denial_reason = (
                denial.get("denial_reason")
                or claim.get("authorization_reason")
                or claim.get("reason")
                or "Denied claim requires review"
            )

            suggestions.append(
                {
                    "field": "denial.authorization",
                    "current": denial_reason,
                    "suggested": (
                        "Verify whether prior authorization or precertification was required "
                        "for the denied service date. If authorization exists, attach proof. "
                        "If not, prepare payer-specific appeal or corrected resubmission."
                    ),
                    "confidence": 0.9,
                    "reason": (
                        "EOB/ERA denial document detected. Authorization/precertification "
                        "denial signals were extracted from the payer response."
                    ),
                }
            )

            suggestions.append(
                {
                    "field": "appeal_strategy",
                    "current": denial_code,
                    "suggested": {
                        "root_cause": "Authorization or precertification missing or not found by payer",
                        "resubmission_strategy": (
                            "Confirm authorization records, attach authorization proof if available, "
                            "or submit appeal with medical necessity and scheduling documentation."
                        ),
                        "appeal_summary": (
                            "The claim was denied because required authorization/precertification "
                            "was not identified. The provider requests reconsideration with supporting "
                            "documentation and any available authorization evidence."
                        ),
                        "prevention": [
                            "Check authorization requirements before service",
                            "Store authorization number on the claim before submission",
                            "Flag CO-197/N382 denials for authorization workflow review",
                        ],
                    },
                    "confidence": 0.88,
                    "reason": "Authorization-related denial signals were extracted from the EOB/ERA document.",
                }
            )

            if denial_code in {"CO-197", "197"} or denial.get("rarc") == "N382":
                suggestions.append(
                    {
                        "field": "denial_code",
                        "current": {
                            "carc": denial.get("carc") or denial_code,
                            "rarc": denial.get("rarc"),
                        },
                        "suggested": {
                            "category": "authorization_missing",
                            "action": "Route to authorization review and appeal preparation",
                        },
                        "confidence": 0.92,
                        "reason": "CO-197/N382 commonly indicates missing authorization or precertification.",
                    }
                )

            return suggestions

        def add(field, suggested, confidence, reason):
            suggestions.append(
                {
                    "field": field,
                    "current": _get_path(claim, field),
                    "suggested": suggested,
                    "confidence": confidence,
                    "reason": reason,
                }
            )

        flat_errors = " ".join(str(error) for error in errors).lower()

        if "cpt" in flat_errors or not claim.get("cpt_codes"):
            add(
                "cpt_codes",
                None,
                0.72,
                "CPT codes are missing or invalid; requires coding review before resubmission.",
            )

        if "icd" in flat_errors or not claim.get("icd_codes"):
            add(
                "icd_codes",
                None,
                0.72,
                "ICD codes are missing or invalid; requires diagnosis coding review.",
            )

        if "npi" in flat_errors or not claim.get("provider", {}).get("npi"):
            add(
                "provider.npi",
                None,
                0.7,
                "Provider NPI missing or invalid; requires provider directory confirmation.",
            )

        if "dob" in flat_errors or not claim.get("patient", {}).get("dob"):
            add(
                "patient.dob",
                None,
                0.68,
                "Patient DOB missing or invalid; confirm demographics from source document.",
            )

        payer = claim.get("payer")
        payer_name = payer.get("name") if isinstance(payer, dict) else payer

        if not payer_name:
            add(
                "payer.name",
                None,
                0.68,
                "Payer name missing; confirm payer from insurance or remittance document.",
            )

        for service in claim.get("services") or []:
            if not isinstance(service, dict):
                continue

            cpt = service.get("cpt") or service.get("cpt_code")

            if cpt and not str(cpt).isdigit():
                add(
                    "services",
                    claim.get("services"),
                    0.74,
                    "Service line CPT formatting requires normalization.",
                )

        return suggestions

    async def _llm_denial_suggestions(
        self,
        claim: Dict[str, Any],
        errors: List[Any],
    ) -> List[Dict[str, Any]]:
        safe_claim = make_json_safe(claim)
        safe_errors = make_json_safe(errors)

        denial = claim.get("denial") if isinstance(claim.get("denial"), dict) else {}

        denial_reason = (
            denial.get("denial_reason")
            or claim.get("authorization_reason")
            or claim.get("reason")
            or "Denied claim requires review"
        )

        denial_code = (
            denial.get("denial_code")
            or denial.get("carc")
            or claim.get("denial_code")
            or "UNKNOWN"
        )

        rarc = denial.get("rarc") or claim.get("rarc") or "UNKNOWN"

        prompt = f"""
Analyze this denied healthcare claim.

Denial code:
{denial_code}

RARC:
{rarc}

Denial reason:
{denial_reason}

Claim:
{json.dumps(safe_claim, indent=2)}

Validation Errors:
{json.dumps(safe_errors, indent=2)}

Suggest:
1. root cause
2. CPT corrections, only if clearly supported by the claim
3. ICD corrections, only if clearly supported by the claim
4. modifiers, only if clearly supported by the claim
5. resubmission strategy
6. appeal summary
7. denial prevention tips

Do not invent patient DOB, CPT, ICD, modifiers, authorization numbers, payer IDs, or service lines.

Return structured JSON with an optional suggestions array containing:
field, current, suggested, confidence, reason.
"""

        try:
            response = await invoke_llm(prompt, expect_json=True)

            if isinstance(response, dict) and isinstance(response.get("suggestions"), list):
                return response["suggestions"]

        except Exception as exc:
            return [
                {
                    "field": "denial_strategy",
                    "current": {
                        "denial_code": denial_code,
                        "rarc": rarc,
                        "denial_reason": denial_reason,
                    },
                    "suggested": {
                        "root_cause": f"{denial_code} / {denial_reason}",
                        "resubmission_strategy": (
                            "Review denial reason, attach supporting documentation, "
                            "correct missing claim details, and resubmit or appeal per payer rules."
                        ),
                        "appeal_summary": (
                            "Claim was reviewed and corrected based on the payer denial reason. "
                            "Supporting documentation should be attached for reconsideration."
                        ),
                        "prevention": [
                            "Validate authorization requirements before service",
                            "Check payer-specific rules before submission",
                            "Require authorization checks before claim submission",
                        ],
                    },
                    "confidence": 0.72,
                    "reason": f"LLM unavailable; fallback denial prevention strategy used: {exc}",
                }
            ]

        return []
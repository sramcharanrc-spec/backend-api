from __future__ import annotations

from typing import Any, Dict

PIPELINE_PROGRESS = {
    "ocr": 15,
    "extraction": 15,
    "eligibility": 30,
    "validation": 45,
    "compliance": 60,
    "submission": 80,
    "clearinghouse": 100,
}

STAGE_ALIASES = {
    "acknowledgment": "clearinghouse",
    "acknowledgement": "clearinghouse",
    "acknowledged": "clearinghouse",
    "clearinghouse_accepted": "clearinghouse",
    "clearinghouse_auto_accepted": "clearinghouse",
    "clearinghouse_queued": "clearinghouse",
    "cms1500": "submission",
    "cms_1500": "submission",
    "edi": "submission",
    "edi837": "submission",
    "edi837p": "submission",
    "edi_837": "submission",
    "edi_837p": "submission",
    "eligibility_checked": "eligibility",
    "eligibility_done": "eligibility",
    "extracted": "ocr",
    "extraction": "ocr",
    "intake": "ocr",
    "ocr": "ocr",
    "pending_clearinghouse": "clearinghouse",
    "rules_validated": "validation",
    "rules_validation": "validation",
    "sending_to_clearinghouse": "submission",
    "ub04": "submission",
    "validated": "validation",
    "validation_agent": "validation",
    "waiting_for_approval": "clearinghouse",
}


def _stage_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _canonical_stage(value: Any) -> str:
    stage = _stage_key(value)
    return STAGE_ALIASES.get(stage, stage)


def normalize_event(
    event: Dict[str, Any]
) -> Dict[str, Any]:
    if not event:
        return {}

    if str(event.get("type") or event.get("event") or "").lower() == "agent_update":
        return assign_progress(dict(event))

    stage = _canonical_stage(
        event.get("stage")
        or
        event.get("current_stage")
        or
        event.get("active_step")
        or
        event.get("step")
        or
        event.get("agent")
        or
        ""
    )

    status = str(
        event.get("status")
        or
        ""
    ).strip().upper()

    normalized = {

        **event,

        "stage": stage,

        "agent": stage,

        "status": status
    }

    return assign_progress(normalized)


def assign_progress(event: Dict[str, Any]) -> Dict[str, Any]:
    if not event:
        return {}

    updated = dict(event)

    try:
        progress = int(
            float(
                updated.get("progress", 0) or 0
            )
        )
    except (TypeError, ValueError):
        progress = 0

    stage = _canonical_stage(
        updated.get("stage")
        or ""
    )

    mapped_progress = PIPELINE_PROGRESS.get(stage)
    if progress > 0:
        updated["progress"] = progress
    elif mapped_progress is not None:
        updated["progress"] = mapped_progress
    else:
        updated["progress"] = 0

    return updated

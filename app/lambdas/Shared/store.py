from __future__ import annotations

from datetime import datetime
from typing import Any

_SUBMISSIONS: dict[str, dict[str, Any]] = {}


def init_db() -> None:
    """Compatibility no-op for older Lambda storage initialization."""
    return None


def save_submission(
    submission_id: str,
    claim_id: str | None = None,
    status: str = "SUBMITTED",
    transmission_id: str | None = None,
    raw_edi: str = "",
    **extra: Any,
) -> dict[str, Any]:
    existing = _SUBMISSIONS.get(submission_id, {})
    record = {
        **existing,
        "submission_id": submission_id,
        "claim_id": claim_id if claim_id is not None else existing.get("claim_id"),
        "status": status,
        "transmission_id": transmission_id if transmission_id is not None else existing.get("transmission_id"),
        "raw_edi": raw_edi,
        "updated_at": datetime.utcnow().isoformat(),
        **extra,
    }
    record.setdefault("created_at", datetime.utcnow().isoformat())
    _SUBMISSIONS[submission_id] = record
    return record


def get_submission(submission_id: str) -> dict[str, Any] | None:
    submission = _SUBMISSIONS.get(submission_id)
    return dict(submission) if submission else None


def get_all_submissions() -> list[dict[str, Any]]:
    return list(_SUBMISSIONS.values())

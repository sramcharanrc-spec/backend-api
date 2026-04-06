# app/rcm/router.py
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List
from dataclasses import asdict

from .orchestrator import submit_claim_from_eda
from .mock_data import SAMPLE_EDA
from .clearinghouse_client import get_submission, list_submissions

router = APIRouter(prefix="/api/rcm", tags=["rcm"])


def _make_json_safe(sub: Any) -> Dict[str, Any]:
    """
    Convert a Submission-like object (dataclass or dict) into a JSON-serializable dict.
    Ensures created_at and status are strings.
    """
    if sub is None:
        return {}
    # dataclass -> dict
    if hasattr(sub, "__dataclass_fields__"):
        d = asdict(sub)
    elif hasattr(sub, "to_dict"):
        d = sub.to_dict()
    elif isinstance(sub, dict):
        d = dict(sub)
    else:
        # fallback: try to use __dict__
        d = dict(getattr(sub, "__dict__", {}))

    # Normalize created_at to ISO string
    ca = d.get("created_at")
    if ca is not None and hasattr(ca, "isoformat"):
        try:
            d["created_at"] = ca.isoformat()
        except Exception:
            d["created_at"] = str(ca)

    # Normalize status to string (support Enum)
    st = d.get("status")
    if st is not None:
        try:
            d["status"] = st.value if hasattr(st, "value") else str(st)
        except Exception:
            d["status"] = str(st)

    # Ensure denial_reason key exists
    if "denial_reason" not in d:
        d["denial_reason"] = None

    return d


@router.post("/submit-sample")
def submit_sample():
    """Submit the in-repo SAMPLE_EDA to the pipeline."""
    result = submit_claim_from_eda(SAMPLE_EDA)
    return result


@router.post("/submit-from-eda")
def submit_from_eda(eda_payload: Dict[str, Any]):
    """
    Submit an arbitrary EDA payload (JSON) to the pipeline.
    Returns the submit result (or raises 400 if validation failed).
    """
    result = submit_claim_from_eda(eda_payload)
    if result.get("status") == "validation_failed":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/run-full-sample")
def run_full_sample():
    """
    Run full flow with SAMPLE_EDA and return both submit_result and the stored submission object.
    """
    result = submit_claim_from_eda(SAMPLE_EDA)
    if result.get("status") == "validation_failed":
        raise HTTPException(status_code=400, detail=result)

    sid = result.get("submission_id")
    sub = get_submission(sid) if sid else None
    return {"submit_result": result, "submission": _make_json_safe(sub) if sub else None}


@router.get("/submission/{sid}")
def get_submission_status(sid: str):
    """Return a JSON-safe representation of a saved submission."""
    sub = get_submission(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return _make_json_safe(sub)


@router.get("/submissions")
def get_submissions(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent submissions (JSON-safe)."""
    items = list_submissions(limit=limit)
    return [_make_json_safe(s) for s in items]

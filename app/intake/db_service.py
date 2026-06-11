import math
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

from psycopg2.extras import Json
from sqlalchemy import text

from app.db.database import engine


# -------------------------
# Helpers
# -------------------------
def utc_now():
    return datetime.utcnow()


def utc_now_iso():
    return utc_now().isoformat()


def generate_claim_id() -> str:
    return f"CLM-{uuid.uuid4().hex[:10]}"


def generate_case_id() -> str:
    return f"CASE-{uuid.uuid4().hex[:10]}"


def clean_nan(obj: Any, visited=None, depth: int = 0, max_depth: int = 30):
    """
    Convert data into JSON-safe payload for PostgreSQL JSON columns.

    Fixes:
    - NaN / Infinity
    - datetime/date
    - Decimal
    - sets/tuples
    - SQLAlchemy/custom objects
    - circular references
    - maximum recursion depth errors
    """

    if visited is None:
        visited = set()

    if depth > max_depth:
        return "[MAX_DEPTH_REACHED]"

    obj_id = id(obj)

    if isinstance(obj, (dict, list, tuple, set)):
        if obj_id in visited:
            return "[CIRCULAR_REFERENCE_REMOVED]"
        visited.add(obj_id)

    try:
        if obj is None:
            return None

        if isinstance(obj, bool):
            return obj

        if isinstance(obj, int):
            return obj

        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj

        if isinstance(obj, Decimal):
            return float(obj)

        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        if isinstance(obj, str):
            return obj

        if isinstance(obj, dict):
            cleaned = {}

            for key, value in obj.items():
                key_str = str(key)

                if key_str.startswith("_"):
                    continue

                # Avoid objects that can cause circular references or huge payloads.
                if key_str in {
                    "db",
                    "session",
                    "manager",
                    "websocket",
                    "request",
                    "response",
                    "response_object",
                    "raw_request",
                    "raw_response",
                    "raw_event",
                    "rawEvent",
                    "self",
                    "parent",
                }:
                    continue

                cleaned[key_str] = clean_nan(
                    value,
                    visited=visited,
                    depth=depth + 1,
                    max_depth=max_depth,
                )

            return cleaned

        if isinstance(obj, (list, tuple, set)):
            return [
                clean_nan(
                    item,
                    visited=visited,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                for item in obj
            ]

        if hasattr(obj, "__dict__"):
            return clean_nan(
                {
                    key: value
                    for key, value in obj.__dict__.items()
                    if not str(key).startswith("_")
                },
                visited=visited,
                depth=depth + 1,
                max_depth=max_depth,
            )

        return str(obj)

    finally:
        if isinstance(obj, (dict, list, tuple, set)):
            visited.discard(obj_id)


def convert_datetime(obj):
    """
    Convert datetime objects to ISO strings recursively.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {k: convert_datetime(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [convert_datetime(i) for i in obj]

    return obj


def convert_floats_to_decimal(obj):
    """
    Legacy DynamoDB helper. Keep only if other files import it.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))

    if isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [convert_floats_to_decimal(i) for i in obj]

    return obj


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _coerce_bool(value):
    if isinstance(value, bool):
        return value

    if value in (1, "1"):
        return True

    return str(value or "").strip().lower() == "true"


def _safe_payload(result: Any) -> dict:
    """
    Prepare payload before saving to DB JSON column.
    Prevents circular reference and recursion failures.
    """

    try:
        cleaned = clean_nan(result or {})

        # Final JSON serialization test.
        json.dumps(cleaned)

        return cleaned

    except Exception as error:
        print(f"❌ Payload cleanup failed: {error}")

        return {
            "payload_error": str(error),
            "payload_type": str(type(result)),
            "payload_preview": f"<unserializable payload type={type(result).__name__}>",
        }


def _extract_claim_payload(cleaned_payload: Dict[str, Any]) -> Dict[str, Any]:
    claim_payload = cleaned_payload.get("claim", cleaned_payload)

    return claim_payload if isinstance(claim_payload, dict) else {}


def _extract_pipeline_payload(cleaned_payload: Dict[str, Any]) -> Dict[str, Any]:
    pipeline_payload = cleaned_payload.get("pipeline", {})

    return pipeline_payload if isinstance(pipeline_payload, dict) else {}


def _json_value(value):
    """
    Psycopg2 JSON wrapper.
    """
    return Json(value if value is not None else {})


# -------------------------
# HITL Case
# -------------------------
def update_case(claim_id, status="OPEN", error=None):
    """
    Create a human-review case for a claim.
    """

    if isinstance(status, dict):
        status = status.get("status", "OPEN")

    if not claim_id:
        raise ValueError("claim_id is required to create a case")

    case_id = generate_case_id()
    description = error or "HITL review required"
    now = utc_now()

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO cases (
                case_id,
                claim_id,
                title,
                description,
                status,
                priority,
                assigned_role,
                created_at,
                updated_at
            )
            VALUES (
                :case_id,
                :claim_id,
                :title,
                :description,
                :status,
                :priority,
                :assigned_role,
                :created_at,
                :updated_at
            )
        """), {
            "case_id": case_id,
            "claim_id": claim_id,
            "title": "Compliance / Validation Review",
            "description": description,
            "status": status,
            "priority": "HIGH",
            "assigned_role": "QA_TEAM",
            "created_at": now,
            "updated_at": now,
        })

    print(f"🧾 Case created: {case_id} for claim {claim_id}")

    return {
        "case_id": case_id,
        "claim_id": claim_id,
        "status": status,
        "description": description,
    }


# -------------------------
# Save single claim
# -------------------------
def save_record(result):
    """
    Insert or update a claim in the claims table.
    """

    try:
        result = result or {}

        claim_id = result.get("claim_id") or generate_claim_id()

        cleaned_payload = _safe_payload(result)
        claim_payload = _extract_claim_payload(cleaned_payload)
        pipeline_payload = _extract_pipeline_payload(cleaned_payload)

        now_iso = utc_now_iso()

        status = _first_present(
            result.get("status"),
            cleaned_payload.get("status"),
            claim_payload.get("status"),
            "NEW",
        )

        stage = _first_present(
            result.get("stage"),
            result.get("current_stage"),
            result.get("active_step"),
            claim_payload.get("current_stage"),
            claim_payload.get("active_step"),
        )

        pipeline_state = _first_present(
            result.get("pipeline_state"),
            result.get("status"),
            pipeline_payload.get("pipeline_state"),
            claim_payload.get("pipeline_state"),
        )

        current_stage = _first_present(
            result.get("current_stage"),
            result.get("stage"),
            pipeline_payload.get("current_stage"),
            claim_payload.get("current_stage"),
            claim_payload.get("active_step"),
        )

        approval_required = _coerce_bool(_first_present(
            result.get("approval_required"),
            pipeline_payload.get("approval_required"),
            claim_payload.get("approval_required"),
            claim_payload.get("review_required"),
        ))

        form_type = _first_present(
            result.get("form_type"),
            result.get("claim_type"),
            claim_payload.get("form_type"),
            claim_payload.get("claim_type"),
        )

        extraction_summary = _first_present(
            result.get("extraction_summary"),
            claim_payload.get("extraction_summary"),
            claim_payload.get("extraction"),
            {},
        )

        ocr_text = _first_present(
            result.get("ocr_text"),
            claim_payload.get("ocr_text"),
            claim_payload.get("extracted_text"),
        )

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO claims (
                    claim_id,
                    status,
                    stage,
                    pipeline_state,
                    current_stage,
                    approval_required,
                    paused_at,
                    approved_at,
                    resumed_at,
                    payload,
                    form_type,
                    ocr_text,
                    extraction_summary,
                    created_at
                )
                VALUES (
                    :claim_id,
                    :status,
                    :stage,
                    :pipeline_state,
                    :current_stage,
                    :approval_required,
                    :paused_at,
                    :approved_at,
                    :resumed_at,
                    :payload,
                    :form_type,
                    :ocr_text,
                    :extraction_summary,
                    :created_at
                )
                ON CONFLICT (claim_id)
                DO UPDATE SET
                    payload = :payload,
                    status = :status,
                    stage = :stage,
                    pipeline_state = :pipeline_state,
                    current_stage = :current_stage,
                    approval_required = :approval_required,
                    paused_at = COALESCE(:paused_at, claims.paused_at),
                    approved_at = COALESCE(:approved_at, claims.approved_at),
                    resumed_at = COALESCE(:resumed_at, claims.resumed_at),
                    form_type = :form_type,
                    ocr_text = :ocr_text,
                    extraction_summary = :extraction_summary,
                    updated_at = NOW()
            """), {
                "claim_id": claim_id,
                "status": status,
                "stage": stage,
                "pipeline_state": pipeline_state,
                "current_stage": current_stage,
                "approval_required": approval_required,
                "paused_at": _first_present(
                    result.get("paused_at"),
                    cleaned_payload.get("paused_at"),
                    claim_payload.get("paused_at"),
                ),
                "approved_at": _first_present(
                    result.get("approved_at"),
                    cleaned_payload.get("approved_at"),
                    claim_payload.get("approved_at"),
                ),
                "resumed_at": _first_present(
                    result.get("resumed_at"),
                    cleaned_payload.get("resumed_at"),
                    claim_payload.get("resumed_at"),
                ),
                "payload": _json_value(cleaned_payload),
                "form_type": form_type,
                "ocr_text": ocr_text,
                "extraction_summary": _json_value(extraction_summary),
                "created_at": now_iso,
            })

        print(f"✅ Saved claim: {claim_id}")

        return claim_id

    except Exception as error:
        print("❌ DB save_record error:", str(error))
        raise


# -------------------------
# List records
# -------------------------
def get_all_records(
    limit=50,
    offset=0,
    search=None,
    status=None,
    sort_by="created_at",
    sort_order="desc",
):
    allowed_sort = {
        "created_at",
        "status",
        "total_charge",
        "updated_at",
    }

    if sort_by not in allowed_sort:
        sort_by = "created_at"

    sort_order = "DESC" if str(sort_order).lower() == "desc" else "ASC"

    query = "SELECT * FROM claims WHERE 1=1"
    params = {
        "limit": limit,
        "offset": offset,
    }

    if search:
        query += """
        AND (
            claim_id ILIKE :search
            OR COALESCE(payload::text, '') ILIKE :search
        )
        """
        params["search"] = f"%{search}%"

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += f"""
        ORDER BY {sort_by} {sort_order}
        LIMIT :limit OFFSET :offset
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = [dict(row._mapping) for row in result]

    print("🔥 ROWS FETCHED:", len(rows))

    return rows


# -------------------------
# Update status
# -------------------------
def update_record_status(
    claim_id,
    status,
    stage=None,
    pipeline_state=None,
    current_stage=None,
):
    """
    Update claim status and optionally stage/pipeline fields.
    """

    if isinstance(claim_id, dict):
        claim_id = claim_id.get("claim_id")

    if isinstance(status, dict):
        status = json.dumps(status)

    if not claim_id:
        raise ValueError("claim_id is required to update claim status")

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE claims
            SET status = :status,
                stage = COALESCE(:stage, stage),
                pipeline_state = COALESCE(:pipeline_state, pipeline_state),
                current_stage = COALESCE(:current_stage, current_stage),
                updated_at = :updated
            WHERE claim_id = :id
        """), {
            "id": claim_id,
            "status": status,
            "stage": stage,
            "pipeline_state": pipeline_state,
            "current_stage": current_stage,
            "updated": utc_now(),
        })

    print(f"🔄 Updated {claim_id} → {status}")


# -------------------------
# Get single record
# -------------------------
def get_record_by_id(claim_id: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT *
            FROM claims
            WHERE claim_id = :id
            LIMIT 1
        """), {
            "id": claim_id,
        })

        row = result.fetchone()

    if not row:
        return None

    record = dict(row._mapping)
    payload = record.get("payload") or {}

    if not isinstance(payload, dict):
        record.setdefault("claim", {})
        record.setdefault("pipeline", {})
        return record

    claim = payload.get("claim", payload)
    pipeline = payload.get("pipeline", {})

    if not isinstance(claim, dict):
        claim = {}

    if not isinstance(pipeline, dict):
        pipeline = {}

    record.setdefault("claim", claim)
    record.setdefault("pipeline", pipeline)

    # Restore commonly used top-level references.
    restore_keys = [
        "pipeline_state",
        "current_stage",
        "submission",
        "ack",
        "acknowledgment",
        "case",
        "validation",
        "compliance",
        "clearinghouse",
        "denial",
        "payment",
        "payment_result",
        "feedback",
        "feedback_data",
        "learning",
        "analytics",
        "generated_artifacts",
        "source_file",
        "intake",
        "extraction",
    ]

    for key in restore_keys:
        value = (
            payload.get(key)
            or claim.get(key)
        )

        if value is not None:
            record.setdefault(key, value)

    record.setdefault(
        "pipeline_state",
        payload.get("pipeline_state")
        or pipeline.get("pipeline_state")
        or claim.get("pipeline_state")
        or record.get("pipeline_state"),
    )

    record.setdefault(
        "current_stage",
        payload.get("current_stage")
        or pipeline.get("current_stage")
        or claim.get("current_stage")
        or record.get("current_stage"),
    )

    return record


# -------------------------
# Update payload
# -------------------------
def update_claim_data(claim_id, updated_data: dict):
    if not claim_id:
        raise ValueError("claim_id is required")

    cleaned_payload = _safe_payload(updated_data or {})

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE claims
            SET payload = :payload,
                updated_at = :updated
            WHERE claim_id = :id
        """), {
            "id": claim_id,
            "payload": _json_value(cleaned_payload),
            "updated": utc_now(),
        })

    print(f"✏️ Claim updated: {claim_id}")


# -------------------------
# Bulk save
# -------------------------
def bulk_save_records(results: List[Dict[str, Any]]):
    try:
        values = []

        for result in results or []:
            result = result or {}

            claim_id = result.get("claim_id") or generate_claim_id()
            cleaned_payload = _safe_payload(result)

            claim_payload = _extract_claim_payload(cleaned_payload)

            values.append({
                "claim_id": claim_id,
                "status": _first_present(
                    result.get("status"),
                    claim_payload.get("status"),
                    "NEW",
                ),
                "stage": _first_present(
                    result.get("stage"),
                    claim_payload.get("current_stage"),
                    claim_payload.get("active_step"),
                ),
                "pipeline_state": _first_present(
                    result.get("pipeline_state"),
                    claim_payload.get("pipeline_state"),
                ),
                "current_stage": _first_present(
                    result.get("current_stage"),
                    claim_payload.get("current_stage"),
                ),
                "payload": _json_value(cleaned_payload),
                "form_type": _first_present(
                    result.get("form_type"),
                    result.get("claim_type"),
                    claim_payload.get("form_type"),
                    claim_payload.get("claim_type"),
                ),
                "ocr_text": _first_present(
                    result.get("ocr_text"),
                    claim_payload.get("ocr_text"),
                    claim_payload.get("extracted_text"),
                ),
                "extraction_summary": _json_value(
                    _first_present(
                        result.get("extraction_summary"),
                        claim_payload.get("extraction_summary"),
                        claim_payload.get("extraction"),
                        {},
                    )
                ),
                "created_at": utc_now_iso(),
            })

        if not values:
            print("⚠️ Bulk save skipped: no records")
            return 0

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO claims (
                    claim_id,
                    status,
                    stage,
                    pipeline_state,
                    current_stage,
                    payload,
                    form_type,
                    ocr_text,
                    extraction_summary,
                    created_at
                )
                VALUES (
                    :claim_id,
                    :status,
                    :stage,
                    :pipeline_state,
                    :current_stage,
                    :payload,
                    :form_type,
                    :ocr_text,
                    :extraction_summary,
                    :created_at
                )
                ON CONFLICT (claim_id)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    status = EXCLUDED.status,
                    stage = EXCLUDED.stage,
                    pipeline_state = EXCLUDED.pipeline_state,
                    current_stage = EXCLUDED.current_stage,
                    form_type = EXCLUDED.form_type,
                    ocr_text = EXCLUDED.ocr_text,
                    extraction_summary = EXCLUDED.extraction_summary,
                    updated_at = NOW()
            """), values)

        print(f"🚀 Bulk saved: {len(values)} claims")

        return len(values)

    except Exception as error:
        print("❌ Bulk DB Error:", str(error))
        raise
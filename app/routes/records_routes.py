from fastapi import APIRouter, Query
from sqlalchemy.exc import SQLAlchemyError

from app.case_management.models.case_models import Case
from app.db.database import SessionLocal
from app.intake.db_service import get_all_records
from app.utils.response_builder import build_clean_response

router = APIRouter()

def _dt(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _nested(source: dict, *keys, default=None):
    cursor = source
    for key in keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
    return cursor if cursor is not None else default


def _compact_payload(record: dict, has_case: bool) -> dict:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else payload
    patient = claim.get("patient") if isinstance(claim.get("patient"), dict) else {}
    payer = claim.get("payer") if isinstance(claim.get("payer"), dict) else {}
    pipeline = payload.get("pipeline") if isinstance(payload.get("pipeline"), dict) else {}

    status = record.get("status") or claim.get("status") or payload.get("status") or "NOT_PROCESSED"
    return {
        "status": status,
        "claim": {
            "patient": {
                "name": patient.get("name") or claim.get("patient_name") or "Unknown",
                "dob": patient.get("dob") or claim.get("patient_dob") or "Unknown",
                "gender": patient.get("gender") or claim.get("gender"),
                "member_id": patient.get("member_id") or claim.get("member_id"),
            },
            "payer": {
                "name": payer.get("name") or claim.get("payer") or claim.get("payer_name") or "Pending",
            },
            "date_of_service": claim.get("date_of_service") or claim.get("dos"),
            "total_charge": claim.get("total_charge") or payload.get("total_charge") or 0,
            "provider": claim.get("provider") if isinstance(claim.get("provider"), dict) else {},
            "status": status,
        },
        "risk_score": _nested(payload, "ai", "risk_score", default=payload.get("risk_score", 0)),
        "current_stage": payload.get("current_stage") or claim.get("current_stage") or pipeline.get("current_stage"),
        "current_agent": payload.get("current_agent") or claim.get("current_agent") or pipeline.get("current_agent"),
        "active_step": payload.get("active_step") or payload.get("current_step") or pipeline.get("active_step"),
        "pipeline_state": payload.get("pipeline_state") or pipeline.get("pipeline_state") or status,
        "progress": payload.get("progress") or pipeline.get("progress"),
        "queue_state": payload.get("queue_state"),
        "review_state": payload.get("review_state"),
        "pipeline_paused": payload.get("pipeline_paused"),
        "processing_mode": payload.get("processing_mode") or claim.get("processing_mode"),
        "upload_mode": payload.get("upload_mode") or claim.get("upload_mode"),
        "upload_source": payload.get("upload_source") or claim.get("upload_source"),
        "claim_type": payload.get("claim_type") or claim.get("claim_type") or claim.get("form_type"),
        "uploaded_at": payload.get("uploaded_at") or claim.get("uploaded_at"),
        "last_activity_at": payload.get("last_activity_at") or claim.get("last_activity_at"),
        "is_new_upload": payload.get("is_new_upload", False),
        "has_case": has_case,
    }


def _record_summary(record: dict, case_claim_ids: set) -> dict | None:
    claim_id = record.get("claim_id")
    if not claim_id:
        return None

    has_case = claim_id in case_claim_ids
    payload = _compact_payload(record, has_case)
    return {
        "claim_id": claim_id,
        "status": record.get("status") or payload.get("status"),
        "created_at": _dt(record.get("created_at")),
        "updated_at": _dt(record.get("updated_at")),
        "uploaded_at": payload.get("uploaded_at"),
        "last_activity_at": payload.get("last_activity_at"),
        "is_new_upload": payload.get("is_new_upload"),
        "queue_state": payload.get("queue_state"),
        "has_case": has_case,
        "payload": payload,
    }


@router.get("/records")
def get_records(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    search: str = "",
    status: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    summary: bool = True
):
    offset = (page - 1) * limit

    records = get_all_records(
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order
    )

    claim_ids = [record.get("claim_id") for record in records if record.get("claim_id")]
    case_claim_ids = set()
    if claim_ids:
        db = SessionLocal()
        try:
            case_claim_ids = {row[0] for row in db.query(Case.claim_id).filter(Case.claim_id.in_(claim_ids)).all()}
        except SQLAlchemyError as exc:
            print("Skipping has_case lookup:", str(exc))
        finally:
            db.close()

    if summary:
        clean_records = []
        for record in records:
            try:
                summarized = _record_summary(record, case_claim_ids)
                if summarized:
                    clean_records.append(summarized)
            except Exception as e:
                print("Skipping bad record:", str(e))

        return {
            "status": "SUCCESS",
            "page": page,
            "limit": limit,
            "count": len(clean_records),
            "records": clean_records
        }

    clean_records = []
    for record in records:
        try:
            clean = build_clean_response(record)
            claim_id = record.get("claim_id") or clean.get("claim_id")

            if not claim_id:
                continue

            payload = record.get("payload") or {}
            if isinstance(payload, dict):
                payload = {**payload, "has_case": claim_id in case_claim_ids}

            clean_records.append({
                "claim_id": claim_id,
                "status": record.get("status"),
                "created_at": record.get("created_at").isoformat() if hasattr(record.get("created_at"), "isoformat") else record.get("created_at"),
                "updated_at": record.get("updated_at").isoformat() if hasattr(record.get("updated_at"), "isoformat") else record.get("updated_at"),
                "uploaded_at": payload.get("uploaded_at") if isinstance(payload, dict) else None,
                "last_activity_at": payload.get("last_activity_at") if isinstance(payload, dict) else None,
                "is_new_upload": payload.get("is_new_upload") if isinstance(payload, dict) else False,
                "queue_state": payload.get("queue_state") if isinstance(payload, dict) else None,
                "has_case": claim_id in case_claim_ids,
                "payload": payload
            })

        except Exception as e:
            print("⚠️ Skipping bad record:", str(e))

    return {
        "status": "SUCCESS",
        "page": page,
        "limit": limit,
        "count": len(clean_records),
        "records": clean_records
    }


@router.get("/api/claims/latest")
def get_latest_claims(limit: int = Query(10, ge=1, le=50)):
    records = get_all_records(limit=limit, offset=0, sort_by="created_at", sort_order="desc")
    claim_ids = [record.get("claim_id") for record in records if record.get("claim_id")]
    case_claim_ids = set()
    if claim_ids:
        db = SessionLocal()
        try:
            case_claim_ids = {row[0] for row in db.query(Case.claim_id).filter(Case.claim_id.in_(claim_ids)).all()}
        except SQLAlchemyError as exc:
            print("Skipping latest has_case lookup:", str(exc))
        finally:
            db.close()

    latest = []
    for record in records:
        summarized = _record_summary(record, case_claim_ids)
        if summarized:
            latest.append(summarized)

    return {"status": "SUCCESS", "count": len(latest), "claims": latest}

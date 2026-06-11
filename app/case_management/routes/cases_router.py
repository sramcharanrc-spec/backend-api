from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.case_management.schemas import AssignmentUpdate, CaseCreate, CommentCreate, StatusUpdate
from app.case_management.services.case_service import CaseService
from app.db.database import get_db
from app.websocket.manager import manager

router = APIRouter(prefix="/cases", tags=["HITL Cases"])


def _service(db: Session) -> CaseService:
    return CaseService(db)


@router.get("")
async def list_cases(
    status: str | None = None,
    assigned_role: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    service = _service(db)
    service.auto_escalate_overdue()
    return [service.serialize_case(case, include_children=False) for case in service.list_cases(status, assigned_role, search, limit)]


@router.get("/dashboard")
async def cases_dashboard(db: Session = Depends(get_db)):
    return _service(db).dashboard()


@router.get("/escalations")
async def cases_escalations(db: Session = Depends(get_db)):
    service = _service(db)
    return [service._serialize_escalation(item) for item in service.escalations()]


@router.get("/by-claim/{claim_id}")
async def get_case_by_claim(claim_id: str, db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case_by_claim(claim_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return service.serialize_case(case, include_children=False)


@router.get("/{case_id}")
async def get_case(case_id: str, db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return service.serialize_case(case)


@router.post("")
async def create_case(payload: CaseCreate, db: Session = Depends(get_db)):
    service = _service(db)
    try:
        case = service.create_case(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = service.serialize_case(case)
    await manager.broadcast({"event": "case_created", "type": "case_created", "case": data, "claim_id": data.get("claim_id")})
    return data


@router.put("/{case_id}/status")
async def update_case_status(case_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        updated = service.update_status(case, payload.status, payload.actor, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = service.serialize_case(updated)
    event = "compliance_review" if payload.status == "COMPLIANCE_REVIEW" else "case_updated"
    await manager.broadcast({"event": event, "type": event, "case": data, "claim_id": data.get("claim_id")})
    return data


@router.put("/{case_id}/assign")
async def assign_case(case_id: str, payload: AssignmentUpdate, db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        updated = service.assign_case(case, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = service.serialize_case(updated)
    await manager.broadcast({"event": "case_assigned", "type": "case_assigned", "case": data, "claim_id": data.get("claim_id")})
    return data


@router.post("/{case_id}/comment")
async def add_comment(case_id: str, payload: CommentCreate, db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    comment = service.add_comment(case, payload.author, payload.role, payload.comment)
    await manager.broadcast({
        "event": "case_comment_added",
        "type": "case_comment_added",
        "case_id": case_id,
        "claim_id": case.claim_id,
        "comment": service._serialize_comment(comment),
    })
    return service.serialize_case(service.get_case(case_id))

@router.post("/{case_id}/escalate")
async def escalate_case(case_id: str, reason: str = "Manual escalation", actor: str = "SYSTEM", db: Session = Depends(get_db)):
    service = _service(db)
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    updated = service.escalate_case(case, reason, actor)
    data = service.serialize_case(updated)
    await manager.broadcast({"event": "case_escalated", "type": "case_escalated", "case": data, "claim_id": data.get("claim_id")})
    return data

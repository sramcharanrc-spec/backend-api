from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.enterprise_observability_service import audit_evidence_for_claim, export_evidence
from app.services.audit_service import get_audit_logs

router = APIRouter()

@router.get("/audit")
def fetch_all():
    return get_audit_logs()

@router.get("/audit/{claim_id}")
def fetch_by_claim(claim_id: str, db: Session = Depends(get_db)):
    evidence = audit_evidence_for_claim(claim_id, db)
    file_logs = get_audit_logs(claim_id)
    evidence["file_audit_logs"] = file_logs
    return evidence


@router.get("/audit/{claim_id}/export")
def export_by_claim(
    claim_id: str,
    format: str = Query("json"),
    db: Session = Depends(get_db),
):
    if format.lower() not in {"json", "csv", "pdf"}:
        raise HTTPException(status_code=400, detail="Unsupported export format")
    evidence = audit_evidence_for_claim(claim_id, db)
    if not evidence.get("timeline") and not evidence.get("decision_logs"):
        raise HTTPException(status_code=404, detail="No audit evidence found for claim")
    body, media_type = export_evidence(evidence, format)
    extension = format.lower()
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{claim_id}-evidence.{extension}"'},
    )

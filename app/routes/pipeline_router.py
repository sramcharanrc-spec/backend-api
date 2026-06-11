from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.pipeline_events_model import PipelineEvent
from app.schemas.pipeline_schema import PipelineEventResponse
from app.utils.serializer import serialize_sqlalchemy_list
from typing import List

router = APIRouter()

@router.get("/pipeline/events", response_model=List[PipelineEventResponse])
async def get_all_pipeline_events(db: Session = Depends(get_db)):
    events = db.query(PipelineEvent).order_by(PipelineEvent.timestamp.desc()).limit(100).all()
    return serialize_sqlalchemy_list(events)

@router.get("/pipeline/{claim_id}", response_model=List[PipelineEventResponse])
async def get_pipeline_events(claim_id: str, db: Session = Depends(get_db)):
    events = db.query(PipelineEvent).filter(PipelineEvent.claim_id == claim_id).order_by(PipelineEvent.timestamp).all()
    return serialize_sqlalchemy_list(events)

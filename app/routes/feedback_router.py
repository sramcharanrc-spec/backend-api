from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.feedback_schema import FeedbackResponse
from app.services.feedback_service import FeedbackService
from app.utils.serializer import serialize_sqlalchemy, serialize_sqlalchemy_list
from typing import List

router = APIRouter()

@router.get("/feedback", response_model=List[FeedbackResponse])
async def get_feedback(db: Session = Depends(get_db)):
    service = FeedbackService(db)
    feedback = service.get_all_feedback()
    return serialize_sqlalchemy_list(feedback)

@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback(feedback_data: dict, db: Session = Depends(get_db)):
    service = FeedbackService(db)
    feedback = service.create_feedback(feedback_data)
    return serialize_sqlalchemy(feedback)

@router.get("/feedback/{claim_id}", response_model=List[FeedbackResponse])
async def get_feedback_by_claim(claim_id: str, db: Session = Depends(get_db)):
    service = FeedbackService(db)
    feedback = service.get_feedback_by_claim(claim_id)
    return serialize_sqlalchemy_list(feedback)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.learning_schema import LearningMetricResponse
from app.services.learning_service import LearningService
from app.utils.serializer import serialize_sqlalchemy_list
from typing import List

router = APIRouter()

@router.get("/learning/metrics", response_model=List[LearningMetricResponse])
async def get_learning_metrics(db: Session = Depends(get_db)):
    service = LearningService(db)
    metrics = service.get_all_metrics()
    return serialize_sqlalchemy_list(metrics)

@router.get("/learning/patterns")
async def get_learning_patterns(db: Session = Depends(get_db)):
    service = LearningService(db)
    patterns = service.get_patterns()
    return {"patterns": patterns}

@router.get("/learning/recommendations")
async def get_learning_recommendations():
    # Placeholder for recommendations based on patterns
    return {"recommendations": ["Improve validation for common denial reasons"]}

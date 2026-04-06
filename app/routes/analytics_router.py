from fastapi import APIRouter
from app.services.analytics_service import get_metrics, get_trends

router = APIRouter(prefix="/analytics")

@router.get("/analytics")
def metrics():
    return get_metrics()

@router.get("/analytics/trends")
def trends():
    return get_trends()
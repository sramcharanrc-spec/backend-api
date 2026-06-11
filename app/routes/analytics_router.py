from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.enterprise_observability_service import enterprise_analytics
from app.services.analytics_service import (
    get_metrics,
    get_trends,
    get_dashboard_analytics,
    get_realtime_summary,
    get_payer_trends,
    get_risk_analytics,
    get_advanced_analytics,
    get_bulk_monitoring,
    get_extraction_analytics,
)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)

# =========================================
# DASHBOARD OVERVIEW
# =========================================

@router.get("/dashboard")
async def dashboard():

    return get_dashboard_analytics()

# =========================================
# KPI SUMMARY
# =========================================

@router.get("/summary")
async def summary():

    return get_realtime_summary()

# =========================================
# CORE ANALYTICS
# =========================================

@router.get("/")
async def analytics():

    return get_metrics()

# =========================================
# TRENDS
# =========================================

@router.get("/trends")
async def trends():

    return get_trends()

# =========================================
# PAYER TRENDS
# =========================================

@router.get("/payer-trends")
async def payer_trends():

    return get_payer_trends()

# =========================================
# RISK ANALYTICS
# =========================================

@router.get("/risk")
async def risk_analytics():

    return get_risk_analytics()


@router.get("/advanced")
async def advanced_analytics():

    return get_advanced_analytics()


@router.get("/bulk")
async def bulk_monitoring():

    return get_bulk_monitoring()


@router.get("/extraction")
async def extraction_analytics():

    return get_extraction_analytics()


@router.get("/enterprise")
async def enterprise(db: Session = Depends(get_db)):

    return enterprise_analytics(db)

# =========================================
# REALTIME PIPELINE METRICS
# =========================================

@router.get("/live")
async def live_pipeline_metrics():

    return {
        "status": "LIVE",
        "message": "Realtime analytics active"
    }

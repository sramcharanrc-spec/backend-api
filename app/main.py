# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from dotenv import load_dotenv

# load_dotenv()

# from app.rcm.rcm_router import router as rcm_router
# from app.lambdas.Shared.store import init_db
# from app.routes.intake_routes import router as intake_router
# from app.websocket.ws_router import router as ws_router
# from app.routes.analytics_router import router as analytics_router
# from app.routes.records_routes import router as records_router
# from app.routes.review_routes import router as review_router
# from app.routes.case_router import router as case_router
# # from app.routes.case_router import router as case_router
# # Create FastAPI app
# app = FastAPI(title="AgenticAI RCM")

# # Register routers
# app.include_router(intake_router, prefix="/intake")
# app.include_router(ws_router)
# app.include_router(rcm_router)
# app.include_router(analytics_router)
# app.include_router(records_router)
# app.include_router(review_router)
# # app.include_router(case_router, prefix='/api')
# app.include_router(case_router, prefix="/api")
# # CORS middleware (IMPORTANT for React/Vite)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:5173",
#         "http://localhost:5174",
#         "http://127.0.0.1:5173",
#         "http://127.0.0.1:5174",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Initialize database
# init_db()

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# -------------------------
# Routers
# -------------------------
from app.rcm.rcm_router import router as rcm_router
from app.routes.intake_routes import router as intake_router
from app.websocket.ws_router import router as ws_router
from app.routes.analytics_router import router as analytics_router
from app.routes.records_routes import router as records_router
from app.routes.review_routes import router as review_router
from app.routes.case_router import router as case_router
from app.lambdas.Shared.store import init_db
from app.api.webhooks import router as webhook_router
from app.routes.feedback_router import router as feedback_router
from app.routes.compliance_router import router as compliance_router
from app.routes.learning_router import router as learning_router
from app.routes.pipeline_router import router as pipeline_router
from app.routes.claims_router import router as claims_router
from app.routes.dashboard import router as dashboard_router
from app.routes.audit_router import router as audit_router
from app.api.job_status import router as job_status_router
from app.db.database import engine
from app.models.base import Base
from app.case_management.routes import router as hitl_cases_router

# Import model modules so SQLAlchemy registers their tables before create_all().
from app.models import (  # noqa: F401
    claim_history_model,
    claim_model,
    clearinghouse_model,
    ai_repair_model,
    compliance_audit_model,
    feedback_model,
    learning_metrics_model,
    payer_model,
    pipeline_events_model,
    enterprise_observability_model,
)
from app.case_management.models import case_models  # noqa: F401

def create_db_tables() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        logger.warning("Skipping automatic table creation: %s", exc)


def ensure_claims_schema() -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS form_type VARCHAR"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS ocr_text TEXT"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS extraction_summary JSONB DEFAULT '{}'::jsonb"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS pipeline_state VARCHAR"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS current_stage VARCHAR"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS approval_required BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMP"))
    except SQLAlchemyError as exc:
        logger.warning("Skipping claims schema compatibility update: %s", exc)

# -------------------------
# App
# -------------------------
app = FastAPI(title="AgenticAI RCM")


# -------------------------
# CORS (FIXED 🔥)
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # 🔥 TEMP fix (avoid CORS errors completely)
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def unhandled_exception_guard(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error",
                "path": request.url.path,
            },
        )


# -------------------------
# Root (DEBUG)
# -------------------------
@app.get("/")
def root():
    return {"status": "RCM Backend Running 🚀"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AgenticAI RCM",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# -------------------------
# Startup Event (FIXED 🔥)
# -------------------------
@app.on_event("startup")
def startup():
    print("Starting RCM Backend...")
    create_db_tables()
    ensure_claims_schema()
    init_db()


# -------------------------
# Routers (ORDER MATTERS)
# -------------------------
app.include_router(ws_router)                 # 🔥 websocket first
app.include_router(intake_router, prefix="/intake")
app.include_router(rcm_router, prefix="/api/rcm")
app.include_router(analytics_router)
app.include_router(records_router)
app.include_router(review_router)
app.include_router(case_router, prefix="/api")
app.include_router(webhook_router)
app.include_router(dashboard_router, prefix="/dashboard")
app.include_router(job_status_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(compliance_router, prefix="/api")
app.include_router(learning_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")
app.include_router(claims_router, prefix="/api")
app.include_router(claims_router)
app.include_router(audit_router, prefix="/api")
app.include_router(hitl_cases_router)
app.include_router(hitl_cases_router, prefix="/api")

for route in app.routes:
    print(route.path)

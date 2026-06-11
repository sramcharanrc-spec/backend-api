from fastapi import APIRouter
from sqlalchemy import text
from app.db.database import engine

router = APIRouter()


@router.get("/stats")
def get_stats():

    with engine.connect() as conn:

        total = conn.execute(text("SELECT COUNT(*) FROM claims")).scalar()
        success = conn.execute(text("SELECT COUNT(*) FROM claims WHERE status='SUCCESS'")).scalar()
        failed = conn.execute(text("SELECT COUNT(*) FROM claims WHERE status='FAILED'")).scalar()

    return {
        "total": total,
        "success": success,
        "failed": failed
    }


@router.get("/cases")
def get_cases():

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT case_id, claim_id, error, status
            FROM cases
            ORDER BY created_at DESC
        """))

        cases = [dict(row._mapping) for row in result]

    return cases
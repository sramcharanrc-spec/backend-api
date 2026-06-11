from fastapi import APIRouter
from rq.job import Job
import redis
import os

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")
conn = redis.from_url(REDIS_URL)


@router.get("/job-status/{job_id}")
def get_job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=conn)

        return {
            "job_id": job_id,
            "status": job.meta.get("status", job.get_status()),
            "steps": job.meta.get("steps", {}),
            "result": job.meta.get("result"),
            "error": job.meta.get("error")
        }

    except Exception as e:
        return {"error": str(e)}
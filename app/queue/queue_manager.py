import os

import redis
from rq import Queue


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")

conn = redis.from_url(
    REDIS_URL,
    decode_responses=False,
)

claim_queue = Queue(
    "claims",
    connection=conn,
    default_timeout=900,
)

claims_queue = claim_queue

dlq_queue = Queue(
    "claims_dlq",
    connection=conn,
    default_timeout=900,
)


def redis_health_check() -> bool:
    try:
        return conn.ping()
    except Exception:
        return False
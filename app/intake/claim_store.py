import uuid
from db import database


async def store_claim_data(data, s3_url):

    claim_id = str(uuid.uuid4())

    await database.execute("""
        INSERT INTO claims (claim_id, data, s3_url, status)
        VALUES ($1, $2, $3, $4)
    """, claim_id, data, s3_url, "UPLOADED")

    return claim_id
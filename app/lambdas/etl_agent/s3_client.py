# # app/rcm/s3_client.py
# import os
# import json
# from typing import Any, Dict

# try:
#     import boto3
#     from botocore.exceptions import BotoCoreError, ClientError
#     _HAS_BOTO = True
# except Exception:
#     _HAS_BOTO = False

# def get_json_from_s3(bucket: str, key: str) -> Dict[str, Any]:
#     """
#     Return JSON object from S3 (bucket/key).
#     Raises an exception if boto3 not available or read fails.
#     """
#     if not _HAS_BOTO:
#         raise RuntimeError("boto3 not installed or available in environment")

#     s3 = boto3.client(
#         "s3",
#         aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
#         aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
#         region_name=os.getenv("AWS_REGION")
#     )

#     try:
#         obj = s3.get_object(Bucket=bucket, Key=key)
#         body = obj["Body"].read()
#         return json.loads(body)
#     except (BotoCoreError, ClientError, ValueError) as exc:
#         raise RuntimeError(f"Failed to read from S3: {exc}") from exc


# def get_sample_json_from_s3_or_raise() -> Dict[str, Any]:
#     """
#     Uses env vars to find sample EDA in S3:
#       S3_SAMPLE_BUCKET and S3_SAMPLE_KEY
#     """
#     bucket = os.getenv("S3_SAMPLE_BUCKET")
#     key = os.getenv("S3_SAMPLE_KEY")
#     if not bucket or not key:
#         raise RuntimeError("S3_SAMPLE_BUCKET or S3_SAMPLE_KEY not set")
#     return get_json_from_s3(bucket, key)
import boto3
import json

s3 = boto3.client("s3")

BUCKET = "healthcare-edi-output"


def load_latest_claim_from_s3(claim_id: str) -> dict:
    prefix = f"claims/{claim_id}/"

    resp = s3.list_objects_v2(
        Bucket=BUCKET,
        Prefix=prefix
    )

    if "Contents" not in resp:
        raise ValueError(f"No claim files found in S3 for {claim_id}")

    latest_obj = max(
        resp["Contents"],
        key=lambda x: x["LastModified"]
    )

    obj = s3.get_object(
        Bucket=BUCKET,
        Key=latest_obj["Key"]
    )

    return json.loads(obj["Body"].read())


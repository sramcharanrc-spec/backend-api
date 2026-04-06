# ehr_pipeline/app/router_ehr.py
import os
import csv
import json
from io import StringIO, TextIOWrapper

import boto3
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

# Read env vars
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")

if not S3_BUCKET:
    # Fail fast at startup so you see the problem clearly
    print("[router_ehr] WARNING: S3_BUCKET is not set. /api/ehr endpoints will raise 500.")


def get_s3_client():
    """
    Create an S3 client. If explicit keys are not set, it will fall back
    to instance/role credentials (IAM role, ECS task role, etc.).
    """
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs.update(
            {
                "aws_access_key_id": AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
            }
        )
    return boto3.client("s3", **kwargs)


s3 = get_s3_client()


@router.get("/schema")
def schema():
    return {
        "required": ["id"],
        "recommended": ["patient_id", "chief_complaint", "assessment", "notes"],
        "notes": "Upload CSV/JSON with at least 'id'. More text improves extraction.",
    }


@router.get("/list")
def list_ehr(prefix: str = Query("ehr/", description="Key prefix inside the bucket")):
    """
    List EHR files from S3 under the given prefix.
    Returns: { items: [ { key: "ehr/file1.json" }, ... ] }
    """
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3_BUCKET not configured on server")

    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        contents = resp.get("Contents", []) or []
        items = [{"key": obj["Key"]} for obj in contents]
        return {"items": items}
    except Exception as e:
        print("[/api/ehr/list] S3 error:", e)
        raise HTTPException(status_code=500, detail=f"S3 list error: {e}")


@router.get("/load")
def load_ehr(key: str = Query(..., description="Exact S3 object key to load")):
    """
    Load one EHR file from S3 and return normalized rows.

    For now we support:
      - .json: array of objects, or single object
      - .ndjson: one JSON per line
      - .csv: parsed via csv.DictReader
    """
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3_BUCKET not configured on server")

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        body = obj["Body"]

        # Try to detect content by extension
        if key.lower().endswith(".json"):
            raw = body.read().decode("utf-8")
            data = json.loads(raw)
            # normalize: ensure it's always a list
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                data = []
            return data

        if key.lower().endswith(".ndjson"):
            text = body.read().decode("utf-8")
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            rows = []
            for ln in lines:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    # skip bad line
                    continue
            return rows

        if key.lower().endswith(".csv"):
            # csv.DictReader expects text stream
            text_stream = TextIOWrapper(body, encoding="utf-8")
            reader = csv.DictReader(text_stream)
            rows = [dict(r) for r in reader]
            return rows

        # Unknown extension: just return empty list or raw?
        # For safety we return empty list.
        return []

    except Exception as e:
        print(f"[/api/ehr/load] Error loading {key}:", e)
        raise HTTPException(status_code=500, detail=f"S3 load error for {key}: {e}")

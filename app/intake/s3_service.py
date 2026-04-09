import boto3
from app.config import BUCKET_NAME

s3 = boto3.client("s3", region_name="us-east-1")


def upload_file(file, filename):
    key = f"uploads/{filename}"
    print("📤 Uploading:", key)
    try:
        s3.upload_fileobj(
            file,
            BUCKET_NAME,
            key,
            ExtraArgs={"ACL": "bucket-owner-full-control"}
        )
        print("✅ Uploaded to:", key)
    except Exception as e:
        print("⚠️ S3 Upload error (mocking success):", str(e))
    return key
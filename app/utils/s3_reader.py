import boto3
import json

s3 = boto3.client("s3")

def load_latest_claim_from_s3(bucket: str, patient_id: str):

    prefix = f"claims/{patient_id}/"

    response = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=prefix
    )

    if "Contents" not in response:
        return None

    latest = sorted(
        response["Contents"],
        key=lambda x: x["LastModified"],
        reverse=True
    )[0]

    obj = s3.get_object(
        Bucket=bucket,
        Key=latest["Key"]
    )

    data = obj["Body"].read().decode("utf-8")

    return json.loads(data)
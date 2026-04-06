# rcm/extract_client.py
import os
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_lambda_client = boto3.client("lambda")

EXTRACTION_LAMBDA_NAME = os.environ.get("EXTRACTION_LAMBDA_NAME", "data-extraction-lambda")

def call_extraction_lambda_for_patient(patient_id: str, session_id: str = None) -> dict:
    """
    Call the Data-Extraction Lambda synchronously.
    Returns a dict with at least: {"status": "...", "message": "...", "patient_id": "...",
    "s3_bucket": "...", "s3_key": "..."} on success (if you applied the small patch above).
    """

    if session_id is None:
        # minimal session id if not provided
        import uuid
        session_id = str(uuid.uuid4())

    # Build the payload shape your extraction lambda expects.
    # The extraction lambda reads parameters either from requestBody content or event["parameters"].
    payload = {
        "sessionId": session_id,
        "parameters": [
            {"name": "patient_id", "value": patient_id},
            {"name": "action_type", "value": "generate"}
        ],
        # optional fields your lambda reads in final response builder
        "actionGroup": "rcm",
        "function": "generateClaim",
        "apiPath": "/generate",
        "httpMethod": "POST"
    }

    logger.info("Invoking extraction lambda '%s' payload=%s", EXTRACTION_LAMBDA_NAME, payload)

    try:
        resp = _lambda_client.invoke(
            FunctionName=EXTRACTION_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
    except ClientError as e:
        logger.exception("Lambda invoke failed")
        raise

    # Read and parse the lambda response payload
    body_bytes = resp["Payload"].read()
    try:
        parsed = json.loads(body_bytes)
    except Exception:
        # fallback decode
        parsed = json.loads(body_bytes.decode("utf-8"))

    # If the extraction lambda returns API-style wrapper {"statusCode":..., "body":"..."}
    if isinstance(parsed, dict) and parsed.get("statusCode") and isinstance(parsed.get("body"), str):
        try:
            parsed = json.loads(parsed["body"])
        except Exception:
            parsed = parsed["body"]

    # Your extraction lambda returns a Bedrock-style final_response (from build_bedrock_response)
    # which contains the actual result under parsed["response"]["responseBody"]["application/json"]["body"]
    try:
        body = parsed.get("response", {}) \
                     .get("responseBody", {}) \
                     .get("application/json", {}) \
                     .get("body", {})
    except Exception:
        body = parsed

    # Body should now contain fields like claim_status, message, final_patient_id, and (after patch) s3_key/s3_bucket
    logger.info("Extraction lambda returned body: %s", body)
    return body

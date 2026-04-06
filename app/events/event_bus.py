# ehr_pipeline/app/events/event_bus.py

import boto3
import json
from app.core.constants import DEFAULT_PAYER

sqs = boto3.client("sqs", region_name="us-east-1")

QUEUE_URL = "YOUR_SQS_QUEUE_URL"


def publish_event(event_type: str, payload: dict):

    message = {
        "type": event_type,
        "payload": payload
    }

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message)
    )
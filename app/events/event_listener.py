# ehr_pipeline/app/events/event_listener.py

import json
import boto3
from app.events.event_types import EventType
from app.agents.validation.validation_agent import ValidationAgent
from app.agents.submission.submission_agent import SubmissionAgent
from app.agents.acknowledgment.acknowledgment_agent import AcknowledgmentAgent
from app.agents.denial.denial_agent import DenialAgent
from app.agents.payment.payment_agent import PaymentAgent
from app.core.retry_handler import execute_with_retry


sqs = boto3.client("sqs", region_name="us-east-1")

QUEUE_URL = "YOUR_SQS_QUEUE_URL"


async def start_event_listener():

    while True:

        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10
        )

        messages = response.get("Messages", [])

        for msg in messages:
            body = json.loads(msg["Body"])
            event_type = body["type"]
            payload = body["payload"]

            await handle_event(event_type, payload)

            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=msg["ReceiptHandle"]
            )


async def handle_event(event_type, payload):

    claim = payload

    if event_type == EventType.CLAIM_CREATED:
        agent = ValidationAgent()
        claim = await agent.run(claim)

    elif event_type == EventType.CLAIM_VALIDATED:
        agent = SubmissionAgent()
        claim = await agent.run(claim)

    elif event_type == EventType.CLAIM_SUBMITTED:
        agent = AcknowledgmentAgent()
        claim = await agent.run(claim)

    elif event_type == EventType.CLAIM_DENIED:
        agent = DenialAgent()
        claim = await agent.run(claim)

    elif event_type == EventType.CLAIM_PAID:
        agent = PaymentAgent()
        claim = await agent.run(claim)
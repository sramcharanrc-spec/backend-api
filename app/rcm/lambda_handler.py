# # lambda_handler.py
# import json
# import os
# from mangum import Mangum

# # Import your FastAPI app object. Adjust path if your app module path differs.
# # In your repo earlier you showed: ehr_pipeline.app.main: app
# # So we import like this:
# from ehr_pipeline.app.main import app  # <-- ensure this is the right import path

# # Create Mangum handler
# handler = Mangum(app)

# # Optional: simple warmup / health wrapper if you want a direct Lambda entry (not used by API Gateway proxy)
# def lambda_health(event, context):
#     return {
#         "statusCode": 200,
#         "headers": {"Content-Type": "application/json"},
#         "body": json.dumps({"ok": True, "msg": "lambda alive"})
#     }

# def handler(event, context):
#     if "Records" in event and "s3" in event["Records"][0]:
#         record = event["Records"][0]
#         bucket = record["s3"]["bucket"]["name"]
#         key = record["s3"]["object"]["key"]

#         pipeline.process_claim_from_s3(bucket, key)
#         return {"status": "RCM pipeline triggered"}


import json
from app.agents.rcm_graph import rcm_graph
from app.utils.s3_reader import extract_claim_from_s3


def lambda_health(event, context):
    return {
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "msg": "lambda_alive"})
    }


def handler(event, context):

    # Handle S3 trigger event
    if "Records" in event and "s3" in event["Records"][0]:

        claim = extract_claim_from_s3(event)

        result = rcm_graph.invoke({
            "claim": claim
        })

        return {
            "status": "RCM pipeline triggered",
            "result": result
        }

    # fallback response
    return {
        "status": "No S3 event received"
    }
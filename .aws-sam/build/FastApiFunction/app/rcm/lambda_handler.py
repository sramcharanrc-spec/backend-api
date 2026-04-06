# lambda_handler.py
import json
import os
from mangum import Mangum

# Import your FastAPI app object. Adjust path if your app module path differs.
# In your repo earlier you showed: ehr_pipeline.app.main: app
# So we import like this:
from ehr_pipeline.app.main import app  # <-- ensure this is the right import path

# Create Mangum handler
handler = Mangum(app)

# Optional: simple warmup / health wrapper if you want a direct Lambda entry (not used by API Gateway proxy)
def lambda_health(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "msg": "lambda alive"})
    }

import json
import boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")


def predict_denial(claim: dict) -> dict:
    """
    Predict denial risk using Bedrock.
    Safe function: does not run at import time.
    """

    prompt = f"""
You are a healthcare RCM denial risk assistant.

Analyze this claim and return JSON only:
{{
  "risk_score": 0.0,
  "risk_level": "LOW|MEDIUM|HIGH",
  "reasons": [],
  "recommended_action": ""
}}

Claim:
{json.dumps(claim, default=str)}
"""

    try:
        response = client.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            }),
        )

        result = json.loads(response["body"].read())
        content = result.get("content", [])

        if content and isinstance(content, list):
            text = content[0].get("text", "{}")
            return json.loads(text)

        return {
            "risk_score": 0.0,
            "risk_level": "UNKNOWN",
            "reasons": ["Empty Bedrock response"],
            "recommended_action": "Manual review if needed",
        }

    except Exception as error:
        return {
            "risk_score": 0.0,
            "risk_level": "UNKNOWN",
            "reasons": [str(error)],
            "recommended_action": "Manual review because denial prediction failed",
        }
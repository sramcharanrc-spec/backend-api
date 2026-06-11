import boto3
import json
import os

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


async def invoke_llm(prompt: str, expect_json=True):
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3
        })

        response = bedrock.invoke_model(modelId=MODEL_ID, body=body)
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"].strip()

        if not expect_json:
            return text

        try:
            return json.loads(text)
        except:
            return {"error": "Invalid JSON", "raw": text}

    except Exception as e:
        return {"error": str(e)}


async def ask_claude_json(prompt: str):
    """Backward-compatible JSON helper used by older intake modules."""
    return await invoke_llm(prompt, expect_json=True)

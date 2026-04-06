import boto3
import json

# Initialize Bedrock client
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


async def ask_claude(prompt: str) -> str:
    """
    Sends prompt to Claude 3 Sonnet via Bedrock
    """
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 500,
            "temperature": 0.3,
            "top_p": 0.9
        })

        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",  # ✅ FIXED
            body=body
        )

        result = json.loads(response["body"].read())

        return result["content"][0]["text"].strip()

    except Exception as e:
        print("❌ Bedrock Error:", str(e))
        return "LLM Error"


async def ask_claude_json(prompt: str):
    """
    Forces Claude to return JSON
    """
    json_prompt = f"""
{prompt}

IMPORTANT:
Return ONLY valid JSON.
No explanation.
"""

    response = await ask_claude(json_prompt)

    try:
        return json.loads(response)
    except Exception:
        return {
            "error": "Failed to parse JSON",
            "raw": response
        }
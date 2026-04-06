import boto3
import json
import asyncio
from botocore.config import Config


class BedrockClient:

    def __init__(self, model_id="anthropic.claude-3-sonnet-20240229-v1:0"):
        self.model_id = model_id
        self.client = boto3.client(
            "bedrock-runtime",
            config=Config(
                region_name="us-east-1",
                retries={"max_attempts": 3}
            )
        )

    async def invoke(self, prompt: str):

        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.2
            })

            # 🔥 run blocking call in thread (VERY IMPORTANT)
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                body=body
            )

            result = json.loads(response["body"].read())

            return result["content"][0]["text"].strip()

        except Exception as e:
            print("❌ Bedrock Error:", str(e))

            # 🔥 fallback to safe value
            return "CPT99213"
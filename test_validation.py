import boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

response = client.converse(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    messages=[
        {
            "role": "user",
            "content": [{"text": "Hello"}]
        }
    ],
    inferenceConfig={"maxTokens": 50}
)

print(response["output"]["message"]["content"][0]["text"])
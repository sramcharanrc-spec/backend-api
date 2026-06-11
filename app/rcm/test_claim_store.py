import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = "Summarize: Patient has fever, cough, and mild fatigue."

response = client.invoke_model(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })
)

result = json.loads(response["body"].read())
print(result)
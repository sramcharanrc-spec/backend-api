import boto3
import json
import asyncio
import re

# bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
   
)


def generate_fix_suggestion(field, error, claim):
    try:
        prompt = f"""
You are a healthcare RCM AI expert.

STRICT RULES:
- Return ONLY valid JSON
- Do NOT include explanation text
- Do NOT include markdown
- Only fix the given field

Claim:
{json.dumps(claim, indent=2)}

Error:
Field: {field}
Issue: {error}

Output format:
{{
  "field": "{field}",
  "suggested_value": "...",
  "confidence": 0.0
}}
"""

        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.2
            }),
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        raw_output = result["content"][0]["text"]

        try:
            match = re.search(r"\{.*\}", raw_output, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                raise ValueError("No JSON found")

        except:
            return {
                "field": field,
                "suggested_value": raw_output.strip(),
                "confidence": 0.5
            }

    except Exception as e:
        print(f"❌ Bedrock error for {field}: {e}")

        return {
            "field": field,
            "suggested_value": None,
            "confidence": 0.0,
            "error": str(e)
        }


# ✅ THIS IS THE IMPORTANT FUNCTION
async def suggest_missing_fields(claim, missing_fields):

    import re

    loop = asyncio.get_running_loop()

    priority_fields = [
        f for f in missing_fields
        if f in ["patient.dob", "provider.npi", "services[0].cpt"]
    ]

    fields_to_process = priority_fields or missing_fields[:3]

    tasks = [
        loop.run_in_executor(
            None,
            generate_fix_suggestion,
            field,
            "Missing or invalid value",
            claim
        )
        for field in fields_to_process
    ]

    results = await asyncio.gather(*tasks)

    # 🔥 CLEAN OUTPUT
    cleaned = []
    for r in results:
        if isinstance(r, dict):
            cleaned.append(r)

    return {
        "suggestions": cleaned
    }
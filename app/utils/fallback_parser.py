import re
import json
import os

import boto3

def extract_icd_codes(text):
    # Matches ICD-10 like Z00.00, E11.9 etc.
    return re.findall(r"\b[A-Z]\d{2}\.\d{1,2}\b", text)


def extract_services(text):
    matches = re.findall(
        r"\bCPT\s*Code:\s*(\d{5})(?:.*?\bCharge:\s*\$?([\d,]+(?:\.\d{1,2})?))?",
        text,
        re.IGNORECASE
    )

    return [
        {
            "cpt": cpt,
            "charge": float(charge.replace(",", "")) if charge else 100,
            "units": 1
        }
        for cpt, charge in matches
    ]

def call_bedrock(prompt):
    region = os.getenv("AWS_REGION", "us-east-1")
    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
    client = boto3.client("bedrock-runtime", region_name=region)

    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }),
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip()

    except Exception as e:
        print(f"Bedrock unavailable: {e}")
        return None


def validate(claim):
    if not isinstance(claim, dict):
        return {
            "valid": False,
            "errors": ["Claim must be a dictionary"]
        }

    errors = []

    if not claim.get("patient", {}).get("name"):
        errors.append("Missing patient name")

    if not claim.get("patient", {}).get("dob"):
        errors.append("Missing patient DOB")

    if not claim.get("provider", {}).get("npi"):
        errors.append("Missing provider NPI")

    if not claim.get("services"):
        errors.append("No services found")

    if not claim.get("cpt_codes"):
        cpt_codes = [
            service.get("cpt")
            for service in claim.get("services", [])
            if service.get("cpt")
        ]
        if cpt_codes:
            claim["cpt_codes"] = cpt_codes
        else:
            errors.append("Missing CPT codes")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def extract_structured_data(raw_text):
    data = {}

    # Patient Name
    name_match = re.search(r"Name:\s*(.+)", raw_text)
    if name_match:
        data["patient_name"] = name_match.group(1).strip()

    services = extract_services(raw_text)
    if services:
        data["services"] = services
        data["cpt_codes"] = [service["cpt"] for service in services]

    # Total Amount
    total_match = re.search(r"Total Amount:\s*\$?(\d+)", raw_text)
    if total_match:
        data["total_amount"] = int(total_match.group(1))

    return data

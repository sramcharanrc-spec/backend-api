import requests

SALESFORCE_URL = "https://your-instance.salesforce.com/services/data/v59.0/sobjects/Case"

def create_case(claim, errors):
    payload = {
        "Subject": "Claim Validation Failed",
        "Description": str(errors),
        "Status": "New"
    }

    headers = {
        "Authorization": "Bearer YOUR_TOKEN"
    }

    response = requests.post(SALESFORCE_URL, json=payload, headers=headers)

    return response.json()
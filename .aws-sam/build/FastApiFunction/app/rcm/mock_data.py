SAMPLE_EDA = {
    "claim_id": "CLM-001",
    "patient": {
        "id": "PT-100",
        "name": "John Demo",
        "dob": "1980-01-01",
        "member_id": "M123456",
    },
    "provider": {
        "npi": "1234567890",
        "name": "Dr. Demo",
    },
    "payer": {
        "id": "TEST-PAYER-1",
        "name": "Optum Test Plan",
    },
    "diagnosis_codes": ["E11.9"],
    "service_date": "2025-01-10",
    "place_of_service": "11",
    "procedure_lines": [
        {"cpt": "99213", "modifier": "25", "charge_amount": 120.0},
    ],
}

# # app/rcm/mock_data.py
# SAMPLE_EDA = {
#     "claim_id": "CLM-123",
#     "patient": {
#         "id": "PT-999",
#         "name": "Test Patient",
#         "dob": "1985-05-05",
#         "member_id": "M999999"
#     },
#     "provider": {
#         "npi": "9999999999",
#         "name": "Dr. Test"
#     },
#     "payer": {"id": "PAYER-1", "name": "Mock Payer"},
#     "diagnosis_codes": ["A10", "B20"],
#     "service_date": "2025-01-01",
#     "procedure_lines": [
#         {"code": "99213", "charge": 100.0}
#     ]
# }

# def get_sample_eda() -> dict:
#     return SAMPLE_EDA.copy()


SAMPLE_EDA = {
    "claim_id": "CLM123",
    "patient": {
        "id": "PT-999",
        "name": "Test Patient",
        "dob": "1985-05-05",
        "member_id": "M99999"
    },
    "provider": {
        "npi": "9999999999",
        "name": "Dr. Test"
    },
    "diagnosis_codes": ["Z00.00"],
    "procedure_lines": [
        {
            "cpt": "99213",
            "charge": 1500
        }
    ]
}

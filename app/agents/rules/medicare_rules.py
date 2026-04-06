def is_not_empty(value):
    return value is not None and value != ""

def is_valid_cpt(value):
    return value and str(value).startswith("CPT")

medicare_rules = [
    {
        "field": "patient_dob",
        "rule": is_not_empty,
        "message": "Patient DOB is required"
    },
    {
        "field": "procedure_code",
        "rule": is_valid_cpt,
        "message": "Invalid CPT code"
    }
]
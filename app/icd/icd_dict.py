# ehr_pipeline/app/icd/icd_dict.py
# Very small demo dictionaries. Extend to real mappings later.

ICD_KEYWORDS = {
    # keyword -> ICD-10
    "fever": "R50.9",
    "cough": "R05.9",
    "diabetes": "E11.9",
    "hypertension": "I10",
    "headache": "R51.9",
    "flu": "J11.1",
    "covid": "U07.1",
}

CPT_KEYWORDS = {
    # keyword -> (CPT, description, default price)
    "cbc": ("85025", "Complete Blood Count", 25.0),
    "xray": ("71045", "Chest X-ray", 80.0),
    "ecg": ("93000", "Electrocardiogram", 45.0),
    "flu test": ("87804", "Influenza assay", 30.0),
    "covid test": ("87635", "COVID-19 PCR", 65.0),
    "consult": ("99213", "Office/outpatient visit est", 95.0),
    "injection": ("96372", "Therapeutic injection", 35.0),
}

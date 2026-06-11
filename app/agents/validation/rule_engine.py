def run_all_rules(claim):
    errors = []

    patient = claim.get("patient") or {}
    provider = claim.get("provider") or {}
    services = claim.get("services") or []

    icd_codes = claim.get("icd_codes") or claim.get("diagnosis_codes") or []
    cpt_codes = claim.get("cpt_codes") or []

    if not icd_codes:
        errors.append("Missing ICD codes")

    if not cpt_codes:
        errors.append("Missing CPT codes")

    if not provider.get("npi") and not provider.get("tax_id"):
        errors.append("Missing provider NPI or Tax ID")

    if not services:
        errors.append("No services found")

    if not patient.get("name"):
        errors.append("Missing patient name")

    if not patient.get("dob"):
        errors.append("Missing patient DOB")

    return errors
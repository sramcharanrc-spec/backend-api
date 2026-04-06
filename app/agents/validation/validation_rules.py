# ehr_pipeline/app/agents/validation/validation_rules.py

def run_basic_rules(claim):

    errors = []

    if not claim.icd_codes:
        errors.append("Missing ICD codes")

    if not getattr(claim, "provider_npi", None):
        errors.append("Missing provider NPI")

    if not claim.cpt_codes:
        errors.append("Missing CPT codes")

    return errors
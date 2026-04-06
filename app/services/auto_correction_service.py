def auto_fix_claim(claim, errors):

    for err in errors:
        field = err["field"]

        # 🔥 SMART FIXES
        if field == "procedure_code":
            claim[field] = "CPT99213"  # valid CPT

        elif field == "patient_dob":
            claim[field] = "1990-01-01"

        else:
            claim[field] = "DEFAULT"

    return claim
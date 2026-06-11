def validate_charges(claim):
    errors = []

    services = claim.get("services", [])
    total = claim.get("total_charge", 0)

    # Rule 1: Missing services
    if not services:
        errors.append("No services found")

    # Rule 2: Zero or negative charges
    for s in services:
        if s.get("charge", 0) <= 0:
            errors.append(f"Invalid charge for CPT {s.get('cpt')}")

    # Rule 3: Total mismatch
    calculated_total = sum(
        s.get("charge", 0) * s.get("units", 1)
        for s in services
    )

    if total and abs(calculated_total - total) > 1:
        errors.append("Total charge mismatch")

    return errors
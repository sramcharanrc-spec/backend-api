def validate_claim(payload: dict) -> dict:
    errors = []

    if not payload.get("claim_id"):
        errors.append("Missing claim_id")

    if not payload.get("patient"):
        errors.append("Missing patient block")

    if not payload.get("provider"):
        errors.append("Missing provider block")

    services = payload.get("services", [])
    if not services:
        errors.append("Missing services")

    for i, svc in enumerate(services):
        try:
            float(svc.get("charge", 0))
        except:
            errors.append(f"Invalid amount in service[{i}]")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

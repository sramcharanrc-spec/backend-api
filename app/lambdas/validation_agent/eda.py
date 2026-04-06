def run_eda(payload: dict) -> list[str]:
    errors = []

    if not payload.get("claim_id"):
        errors.append("Missing claim_id")

    if not payload.get("patient"):
        errors.append("Missing patient block")

    if not payload.get("provider"):
        errors.append("Missing provider block")

    if not payload.get("services"):
        errors.append("Missing services")

    return errors

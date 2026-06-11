import secrets


def generate_claim_id() -> str:
    """
    Generate a stable claim ID for internal pipeline tracking.

    Example:
        CLM-9b3a14e852
    """
    return f"CLM-{secrets.token_hex(5)}"
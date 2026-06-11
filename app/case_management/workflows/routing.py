def recommend_route(status: str, risk_score: float, compliance_flags: list[str] | None = None) -> str:
    compliance_flags = compliance_flags or []
    if status == "LEGAL_REVIEW" or risk_score >= 85:
        return "Legal Team"
    if status == "COMPLIANCE_REVIEW" or compliance_flags:
        return "Compliance Team"
    if risk_score >= 65:
        return "HEOR Team"
    return "MA Team"


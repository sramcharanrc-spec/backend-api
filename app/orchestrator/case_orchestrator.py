from datetime import datetime, timedelta
from uuid import uuid4


# -------------------------------------------------
# Role / SLA config
# -------------------------------------------------

SLA_CONFIG = {
    "MA": 2,       # Medical Assistant / front-office review
    "HEOR": 6,    # High-risk / revenue / outcomes review
    "LEGAL": 12,  # Legal/compliance review
}

VALID_ROLES = set(SLA_CONFIG.keys())


def utc_now() -> datetime:
    return datetime.utcnow()


def safe_float(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def as_list(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    return [value]


def get_claim_id(claim: dict) -> str:
    return str(
        claim.get("claim_id")
        or claim.get("claimId")
        or claim.get("submission_id")
        or "UNKNOWN"
    )


def calculate_sla(role: str) -> str:
    role = role if role in VALID_ROLES else "MA"
    hours = SLA_CONFIG.get(role, 2)
    return (utc_now() + timedelta(hours=hours)).isoformat()


# -------------------------------------------------
# Determine case assignment
# -------------------------------------------------

def determine_assignee(claim: dict, denial: dict = None, issues: list = None) -> str:
    claim = claim or {}
    denial = denial or {}
    issues = issues or []

    compliance = (
        claim.get("compliance")
        or claim.get("compliance_results")
        or {}
    )

    risk_score = safe_float(
        denial.get("risk_score")
        or denial.get("risk")
        or compliance.get("risk_score")
        or claim.get("risk_score")
        or 0
    )

    text_blob = f"{claim} {denial} {issues}".lower()

    hard_reject = (
        claim.get("hard_reject") is True
        or claim.get("compliance_status") == "HARD_REJECT"
        or compliance.get("hard_reject") is True
    )

    legal_issue = (
        claim.get("audit_flag")
        or hard_reject
        or "legal" in text_blob
        or "hipaa" in text_blob
        or "fraud" in text_blob
        or "blacklisted" in text_blob
    )

    if legal_issue:
        return "LEGAL"

    if risk_score > 0.7:
        return "HEOR"

    return "MA"


# -------------------------------------------------
# Determine case priority
# -------------------------------------------------

def determine_priority(claim: dict, denial: dict = None, issues: list = None) -> str:
    claim = claim or {}
    denial = denial or {}
    issues = issues or []

    compliance = (
        claim.get("compliance")
        or claim.get("compliance_results")
        or {}
    )

    risk_score = safe_float(
        denial.get("risk_score")
        or compliance.get("risk_score")
        or claim.get("risk_score")
        or 0
    )

    hard_reject = (
        claim.get("hard_reject") is True
        or claim.get("compliance_status") == "HARD_REJECT"
        or compliance.get("hard_reject") is True
    )

    hitl_required = (
        claim.get("hitl_required") is True
        or claim.get("compliance_status") == "HITL_REQUIRED"
        or compliance.get("hitl_required") is True
    )

    if hard_reject:
        return "CRITICAL"

    if hitl_required or risk_score > 0.8:
        return "HIGH"

    if risk_score > 0.5 or issues:
        return "MEDIUM"

    return "LOW"


# -------------------------------------------------
# Case reason builder
# -------------------------------------------------

def build_case_reasons(claim: dict, denial: dict = None, issues: list = None) -> list:
    claim = claim or {}
    denial = denial or {}
    issues = as_list(issues)

    compliance = (
        claim.get("compliance")
        or claim.get("compliance_results")
        or {}
    )

    validation = claim.get("validation") or {}

    reasons = []

    if claim.get("hitl_required") or compliance.get("hitl_required"):
        reasons.append("HITL review required")

    if claim.get("hard_reject") or compliance.get("hard_reject"):
        reasons.append("Hard reject requires review")

    if claim.get("compliance_status") in {"HITL_REQUIRED", "HARD_REJECT"}:
        reasons.append(f"Compliance status: {claim.get('compliance_status')}")

    validation_errors = (
        validation.get("errors")
        or claim.get("validation_errors")
        or []
    )

    if validation_errors:
        reasons.append("Validation errors found")

    failed_rules = (
        compliance.get("failed_rules")
        or compliance.get("failures")
        or []
    )

    if failed_rules:
        reasons.append("Compliance failed rules found")

    risk_score = safe_float(
        denial.get("risk_score")
        or denial.get("risk")
        or compliance.get("risk_score")
        or claim.get("risk_score")
        or 0
    )

    if risk_score > 0.7:
        reasons.append("High denial/compliance risk")

    if not (claim.get("patient") or {}).get("dob"):
        reasons.append("Missing patient DOB")

    for issue in issues:
        if isinstance(issue, dict):
            message = issue.get("reason") or issue.get("message") or issue.get("rule")
            if message:
                reasons.append(str(message))
        else:
            reasons.append(str(issue))

    # Deduplicate while preserving order
    seen = set()
    unique = []

    for reason in reasons:
        clean = str(reason).strip()
        if clean and clean not in seen:
            unique.append(clean)
            seen.add(clean)

    return unique


# -------------------------------------------------
# Escalation engine
# -------------------------------------------------

def check_escalation(case: dict) -> dict:
    if not case or not case.get("sla_due"):
        return case

    try:
        sla_due = datetime.fromisoformat(case["sla_due"])
    except (TypeError, ValueError):
        case["sla_due"] = calculate_sla(case.get("assigned_to", "MA"))
        return case

    now = utc_now()

    if now <= sla_due:
        return case

    current_level = int(case.get("escalation_level") or 0)
    next_level = current_level + 1

    case["escalation_level"] = next_level

    if next_level == 1:
        case["assigned_to"] = "HEOR"
    else:
        case["assigned_to"] = "LEGAL"

    case["sla_due"] = calculate_sla(case["assigned_to"])
    case["status"] = "ESCALATED"
    case["updated_at"] = now.isoformat()

    case.setdefault("history", []).append({
        "action": "ESCALATED",
        "assigned_to": case["assigned_to"],
        "escalation_level": next_level,
        "timestamp": now.isoformat(),
    })

    print(f"🚨 Escalated → {case['assigned_to']}")

    return case


# -------------------------------------------------
# Build case record
# -------------------------------------------------

def build_case_record(claim: dict, denial: dict = None, issues: list = None) -> dict:
    claim = claim or {}
    denial = denial or {}
    issues = as_list(issues)

    now = utc_now()
    claim_id = get_claim_id(claim)

    case_reasons = build_case_reasons(claim, denial, issues)
    assigned_role = determine_assignee(claim, denial, issues)
    priority = determine_priority(claim, denial, issues)

    case_id = f"CASE-{claim_id}-{uuid4().hex[:8]}"

    case = {
        "case_id": case_id,
        "claim_id": claim_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),

        "claim": claim,
        "denial": denial,

        "assigned_to": assigned_role,
        "priority": priority,
        "sla_due": calculate_sla(assigned_role),
        "escalation_level": 0,

        "signature": None,
        "status": "OPEN",

        "issues": issues,
        "case_reasons": case_reasons,

        "review_required": True,
        "approval_required": True,
        "pipeline_paused": True,

        "history": [
            {
                "action": "CASE_CREATED",
                "assigned_to": assigned_role,
                "priority": priority,
                "case_reasons": case_reasons,
                "timestamp": now.isoformat(),
            }
        ],
    }

    return case


# -------------------------------------------------
# Route helper
# -------------------------------------------------

def determine_case_route(claim: dict) -> str:
    claim = claim or {}

    denial = (
        claim.get("denial")
        or claim.get("denial_risk")
        or claim.get("denial_analysis")
        or {}
    )

    return determine_assignee(claim, denial)
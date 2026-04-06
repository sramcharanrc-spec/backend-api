from datetime import datetime, timedelta

ROLE_RULES = {
    "needs_review": "MA",
    "high_risk": "HEOR",
    "legal_issue": "LEGAL",
    "completed": None
}

# 🎯 SLA CONFIG (in hours)
SLA_CONFIG = {
    "MA": 2,
    "HEOR": 6,
    "LEGAL": 12
}


# 🧠 1. DETERMINE ASSIGNEE (ENHANCED 🔥)
def determine_assignee(claim: dict, denial: dict):

    # 🔥 Legal condition
    if claim.get("audit_flag") or "legal" in str(claim).lower():
        return "LEGAL"

    # 🔥 High risk
    if denial and denial.get("risk_score", 0) > 0.7:
        return "HEOR"

    return "MA"


# ⏱️ 2. CALCULATE SLA
def calculate_sla(role: str) -> str:
    hours = SLA_CONFIG.get(role, 2)
    return (datetime.utcnow() + timedelta(hours=hours)).isoformat()


# 🚨 3. ESCALATION ENGINE (UPGRADED 🔥)
def check_escalation(case: dict) -> dict:

    if not case or not case.get("sla_due"):
        return case

    now = datetime.utcnow()
    sla_due = datetime.fromisoformat(case["sla_due"])

    # ⛔ Not yet breached
    if now <= sla_due:
        return case

    case["escalation_level"] = case.get("escalation_level", 0) + 1

    # 🔁 Escalation logic
    if case["escalation_level"] == 1:
        case["assigned_to"] = "HEOR"

    elif case["escalation_level"] >= 2:
        case["assigned_to"] = "LEGAL"

    # 🔄 Reset SLA
    case["sla_due"] = calculate_sla(case["assigned_to"])

    # 🔥 ADD STATUS
    case["status"] = "ESCALATED"

    # 🔥 ADD HISTORY (AUDIT TRAIL)
    case.setdefault("history", []).append({
        "action": "ESCALATED",
        "assigned_to": case["assigned_to"],
        "timestamp": datetime.utcnow().isoformat()
    })

    print(f"🚨 Escalated → {case['assigned_to']}")

    return case


# 🏗️ 4. BUILD CASE RECORD (UPGRADED 🔥)
def build_case_record(claim: dict, denial: dict = None, issues: list = None):

    assigned_role = determine_assignee(claim, denial)

    case = {
        "case_id": f"CASE-{int(datetime.utcnow().timestamp())}",
        "created_at": datetime.utcnow().isoformat(),

        "claim": claim,
        "denial": denial,

        "assigned_to": assigned_role,
        "sla_due": calculate_sla(assigned_role),
        "escalation_level": 0,

        "signature": None,
        "status": "OPEN",

        # 🔥 NEW (HITL SUPPORT)
        "issues": issues or [],

        # 🔥 NEW (AUDIT HISTORY)
        "history": [
            {
                "action": "CASE_CREATED",
                "assigned_to": assigned_role,
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    }

    return case


# 🧠 OPTIONAL: ROUTE HELPER (NO CHANGE)
def determine_case_route(claim):
    risk = claim.get("denial", {}).get("risk_score", 0)

    if risk >= 0.7:
        return "HEOR"
    elif "legal" in str(claim).lower():
        return "LEGAL"
    return "MA"
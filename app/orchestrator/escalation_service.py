# ehr_pipeline/app/orchestrator/escalation_service.py

from datetime import datetime, timedelta


SLA_CONFIG = {
    "MA": 2,
    "HEOR": 6,
    "SUPERVISOR": 4,
    "LEGAL": 12,
}


def utc_now() -> datetime:
    return datetime.utcnow()


def calculate_sla(role: str) -> str:
    role = str(role or "MA").upper()
    hours = SLA_CONFIG.get(role, 2)
    return (utc_now() + timedelta(hours=hours)).isoformat()


def _parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def evaluate_escalation(case: dict):
    """
    Escalates an open case if its SLA is breached.

    Escalation path:
    Level 0 -> current assignee
    Level 1 -> HEOR
    Level 2+ -> LEGAL
    """

    if not case:
        return None

    if not isinstance(case, dict):
        raise ValueError("case must be a dictionary")

    sla_due = _parse_datetime(case.get("sla_due"))

    if not sla_due:
        case["sla_due"] = calculate_sla(case.get("assigned_to", "MA"))
        case["updated_at"] = utc_now().isoformat()
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

    case["status"] = "ESCALATED"
    case["sla_due"] = calculate_sla(case["assigned_to"])
    case["updated_at"] = now.isoformat()

    case.setdefault("history", []).append({
        "action": "ESCALATED",
        "assigned_to": case["assigned_to"],
        "escalation_level": next_level,
        "previous_sla_due": sla_due.isoformat(),
        "new_sla_due": case["sla_due"],
        "timestamp": now.isoformat(),
    })

    return case
from datetime import datetime

def evaluate_escalation(case):

    if not case:   # 🔥 FIX
        return None

    if not case.get("sla_due"):
        return case

    from datetime import datetime

    now = datetime.utcnow()
    sla_due = datetime.fromisoformat(case["sla_due"])

    if now > sla_due:
        case["escalation_level"] = case.get("escalation_level", 0) + 1

        if case["escalation_level"] == 1:
            case["assigned_to"] = "SUPERVISOR"
        elif case["escalation_level"] >= 2:
            case["assigned_to"] = "LEGAL"

        case["sla_due"] = datetime.utcnow().isoformat()
        case["status"] = "ESCALATED"

    return case
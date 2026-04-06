import datetime

analytics_store = {
    "events": []
}

def update_metrics(event_type):

    analytics_store["events"].append({
        "type": event_type,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })


def get_metrics():

    total = len(analytics_store["events"])

    denials = sum(1 for e in analytics_store["events"] if e["type"] == "denial")
    payments = sum(1 for e in analytics_store["events"] if e["type"] == "payment")
    validation_failures = sum(1 for e in analytics_store["events"] if e["type"] == "validation_failed")

    approval_rate = (payments / total * 100) if total > 0 else 0

    return {
        "total_claims": total,
        "denials": denials,
        "payments": payments,
        "validation_failures": validation_failures,
        "approval_rate": round(approval_rate, 2)
    }


def get_trends():

    trend = {}

    for e in analytics_store["events"]:
        date = e["timestamp"][:10]

        if date not in trend:
            trend[date] = {"denial": 0, "payment": 0}

        if e["type"] == "denial":
            trend[date]["denial"] += 1

        if e["type"] == "payment":
            trend[date]["payment"] += 1

    return trend
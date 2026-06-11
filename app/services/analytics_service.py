import datetime
from collections import defaultdict

# =========================================
# GLOBAL ANALYTICS STORE
# =========================================

analytics_store = {
    "events": [],
    "claims": {},
    "agents": defaultdict(int),
    "payers": defaultdict(int),
    "risk_scores": [],
    "latencies": [],
    "denial_reasons": defaultdict(int),
    "sla": {"overdue": 0, "due_soon": 0, "met": 0},
    "escalations": defaultdict(int),
    "batches": {},
    "extraction": {
        "ocr_quality": [],
        "extraction_confidence": [],
        "validation_score": [],
        "service_confidence": [],
        "form_types": defaultdict(int),
        "low_confidence": 0,
    },
}

# =========================================
# UPDATE METRICS
# =========================================

def update_metrics(
    event_type,
    claim_id=None,
    agent=None,
    payer=None,
    risk_score=0,
    latency=0,
    status=None,
):

    event = {
        "type": event_type,
        "claim_id": claim_id,
        "agent": agent,
        "payer": payer,
        "risk_score": risk_score,
        "latency": latency,
        "status": status,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    analytics_store["events"].append(event)

    if claim_id:

        analytics_store["claims"][claim_id] = {
            "status": status,
            "risk_score": risk_score,
            "payer": payer,
            "agent": agent,
            "updated_at": event["timestamp"]
        }

    if agent:
        analytics_store["agents"][agent] += 1

    # =========================================
    # SAFE PAYER HANDLING
    # =========================================

    if payer:

        try:

            # payer can sometimes arrive as dict
            if isinstance(payer, dict):

                payer_name = (
                    payer.get("name")
                    or payer.get("payer_name")
                    or payer.get("company")
                    or "Unknown"
                )

            else:
                payer_name = str(payer)

        except Exception:
            payer_name = "Unknown"

        analytics_store["payers"][payer_name] += 1

    if risk_score:
        analytics_store["risk_scores"].append(risk_score)

    if latency:
        analytics_store["latencies"].append(latency)

    if event_type in {"denial", "denial_detected"}:
        reason = status or "Unknown"
        analytics_store["denial_reasons"][reason] += 1

    if event_type in {"case_escalated", "sla_warning"}:
        analytics_store["escalations"][status or "case"] += 1


def update_batch_metrics(batch_id, total=0, processed=0, failed=0, retries=0, active_workers=0):
    percent = round((processed / total) * 100, 2) if total else 0
    analytics_store["batches"][batch_id] = {
        "batch_id": batch_id,
        "total": total,
        "processed": processed,
        "failed": failed,
        "retries": retries,
        "active_workers": active_workers,
        "progress_percent": percent,
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }


def update_extraction_metrics(form_type=None, ocr_quality=0, extraction_confidence=0, validation_score=0, service_confidence=0, low_confidence=False):
    extraction = analytics_store["extraction"]
    if form_type:
        extraction["form_types"][form_type] += 1
    for key, value in {
        "ocr_quality": ocr_quality,
        "extraction_confidence": extraction_confidence,
        "validation_score": validation_score,
        "service_confidence": service_confidence,
    }.items():
        if value:
            extraction[key].append(float(value))
    if low_confidence:
        extraction["low_confidence"] += 1

# =========================================
# DASHBOARD ANALYTICS
# =========================================

def get_dashboard_analytics():

    total_claims = len(analytics_store["claims"])

    payments = len([
        e for e in analytics_store["events"]
        if e["type"] == "payment"
    ])

    denials = len([
        e for e in analytics_store["events"]
        if e["type"] == "denial"
    ])

    compliance_failures = len([
        e for e in analytics_store["events"]
        if e["type"] == "compliance_failed"
    ])

    approval_rate = (
        (payments / total_claims) * 100
        if total_claims > 0 else 0
    )

    return {
        "total_claims": total_claims,
        "payments": payments,
        "denials": denials,
        "approval_rate": round(approval_rate, 2),
        "compliance_failures": compliance_failures,
    }

# =========================================
# REALTIME SUMMARY
# =========================================

def get_realtime_summary():

    return get_dashboard_analytics()

# =========================================
# CORE METRICS
# =========================================

def get_metrics():

    total = len(analytics_store["events"])

    denials = sum(
        1 for e in analytics_store["events"]
        if e["type"] == "denial"
    )

    payments = sum(
        1 for e in analytics_store["events"]
        if e["type"] == "payment"
    )

    validation_failures = sum(
        1 for e in analytics_store["events"]
        if e["type"] == "validation_failed"
    )

    approval_rate = (
        (payments / total * 100)
        if total > 0 else 0
    )

    return {
        "total_claims": total,
        "denials": denials,
        "payments": payments,
        "validation_failures": validation_failures,
        "approval_rate": round(approval_rate, 2)
    }

# =========================================
# TRENDS
# =========================================

def get_trends():

    trend = {}

    for e in analytics_store["events"]:

        date = e["timestamp"][:10]

        if date not in trend:

            trend[date] = {
                "denial": 0,
                "payment": 0
            }

        if e["type"] == "denial":
            trend[date]["denial"] += 1

        if e["type"] == "payment":
            trend[date]["payment"] += 1

    return trend

# =========================================
# PAYER TRENDS
# =========================================

def get_payer_trends():

    return [
        {
            "payer": payer,
            "count": count
        }
        for payer, count
        in analytics_store["payers"].items()
    ]

# =========================================
# RISK ANALYTICS
# =========================================

def get_risk_analytics():

    high = 0
    medium = 0
    low = 0

    for score in analytics_store["risk_scores"]:

        if score >= 70:
            high += 1

        elif score >= 30:
            medium += 1

        else:
            low += 1

    return {
        "high_risk": high,
        "medium_risk": medium,
        "low_risk": low
    }


def get_advanced_analytics():
    latencies = analytics_store["latencies"]
    risk_scores = analytics_store["risk_scores"]
    total_events = len(analytics_store["events"])
    agent_total = sum(analytics_store["agents"].values()) or 1

    return {
        "denial_trends": dict(analytics_store["denial_reasons"]),
        "payer_trends": get_payer_trends(),
        "sla_metrics": analytics_store["sla"],
        "escalation_analytics": dict(analytics_store["escalations"]),
        "risk_distribution": get_risk_analytics(),
        "throughput": {
            "events": total_events,
            "claims": len(analytics_store["claims"]),
            "events_per_claim": round(total_events / max(len(analytics_store["claims"]), 1), 2),
        },
        "pipeline_latency": {
            "avg_seconds": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "max_seconds": max(latencies) if latencies else 0,
        },
        "agent_performance": [
            {
                "agent": agent,
                "executions": count,
                "share": round((count / agent_total) * 100, 2),
            }
            for agent, count in analytics_store["agents"].items()
        ],
        "risk_average": round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0,
        "bulk_batches": list(analytics_store["batches"].values()),
        "extraction_quality": get_extraction_analytics(),
    }


def get_bulk_monitoring():
    return {
        "active_workers": sum(batch.get("active_workers", 0) for batch in analytics_store["batches"].values()),
        "failed_claims": sum(batch.get("failed", 0) for batch in analytics_store["batches"].values()),
        "retry_counts": sum(batch.get("retries", 0) for batch in analytics_store["batches"].values()),
        "batches": list(analytics_store["batches"].values()),
    }


def get_extraction_analytics():
    extraction = analytics_store["extraction"]

    def avg(values):
        return round(sum(values) / len(values), 2) if values else 0

    return {
        "ocr_accuracy": avg(extraction["ocr_quality"]),
        "extraction_quality": avg(extraction["extraction_confidence"]),
        "validation_confidence": avg(extraction["validation_score"]),
        "service_extraction": avg(extraction["service_confidence"]),
        "low_confidence_count": extraction["low_confidence"],
        "form_success_rate": round(100 - (extraction["low_confidence"] / max(sum(extraction["form_types"].values()), 1) * 100), 2),
        "form_types": dict(extraction["form_types"]),
    }

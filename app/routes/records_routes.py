from fastapi import APIRouter
from app.intake.db_service import get_all_records
from app.utils.response_builder import build_clean_response

router = APIRouter()

@router.get("/records")
def get_records(summary: bool = True):

    records = get_all_records()
    clean_records = []

    for record in records:

        # 🔥 Skip empty records
        if not record:
            continue

        try:
            clean = build_clean_response(record)

            # 🔥 Skip invalid claim_id
            if not clean.get("claim_id"):
                continue

            if summary:
                patient = clean.get("claim", {}).get("patient", {})
                risk = clean.get("ai", {}).get("risk_score")

                # ✅ FIX HERE
                status = clean.get("status")

                financial_status = clean.get("financials", {}).get("status")

                clean = {
                    "claim_id": clean.get("claim_id"),

                    "patient": {
                        "name": patient.get("name") or "Unknown",
                        "dob": patient.get("dob") or "Unknown"
                    },

                    # ✅ NOW THIS WORKS
                    "status": status or "NOT_PROCESSED",

                    "risk_score": risk if risk is not None else 0,
                    "financial_status": financial_status or "PENDING"
            }

            clean_records.append(clean)

        except Exception as e:
            print("⚠️ Skipping bad record:", str(e))

    return {
        "status": "SUCCESS",
        "count": len(clean_records),
        "records": clean_records
    }
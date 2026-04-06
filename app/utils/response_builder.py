def build_clean_response(raw_data: dict):

    # ✅ Safe copies
    claim = dict(raw_data.get("claim") or {})
    pipeline = dict(raw_data.get("pipeline") or {})
    case_data = raw_data.get("case") or {}
    payment = dict(raw_data.get("payment") or {})
    validation = dict(raw_data.get("validation") or {})  # 🔥 FIXED (not pipeline)

    denial_risk = claim.get("denial_risk", {})

    # -----------------------------------
    # 🔥 FIX 0: PRESERVE ORIGINAL STATUS
    # -----------------------------------
    final_status = raw_data.get("status", "SUCCESS")

    # -----------------------------------
    # ✅ FIX 1: Remove duplicate claim data
    # -----------------------------------
    pipeline.pop("claim", None)
    case_data.pop("claim", None)
    validation.pop("claim", None)

    # -----------------------------------
    # ✅ FIX 2: Validation logic
    # -----------------------------------
    errors = validation.get("errors", []) if validation else []

    if claim.get("patient", {}).get("name") == "Unknown":
        errors.append({
            "field": "patient.name",
            "message": "Patient name missing"
        })

    if not claim.get("provider", {}).get("npi"):
        errors.append({
            "field": "provider.npi",
            "message": "Provider NPI missing"
        })

    is_valid = len(errors) == 0

    # -----------------------------------
    # 🔥 FIX 3: FORCE HITL IF INVALID
    # -----------------------------------
    if not is_valid:
        final_status = "HITL_REQUIRED"

    # -----------------------------------
    # ✅ FIX 4: Correct pipeline steps
    # -----------------------------------
    steps = dict(pipeline.get("steps") or {})
    steps["rules_validated"] = is_valid

    # -----------------------------------
    # ✅ FIX 5: Financial cleanup
    # -----------------------------------
    reconciliation = payment.get("reconciliation", {})

    claim.pop("reconciliation", None)
    claim.pop("payment_status", None)

    # -----------------------------------
    # ✅ FIX 6: Total charge correction
    # -----------------------------------
    if claim.get("calculated_total"):
        claim["total_charge"] = claim["calculated_total"]
        claim.pop("calculated_total", None)

    # -----------------------------------
    # ✅ FIX 7: Validation status
    # -----------------------------------
    validation_status = "passed" if is_valid else "failed"

    # -----------------------------------
    # 🔥 FIX 8: CLEAN CASE OUTPUT
    # -----------------------------------
    clean_case = None
    if case_data and case_data.get("case_id"):
        clean_case = {
            "case_id": case_data.get("case_id"),
            "status": case_data.get("status"),
            "assigned_to": case_data.get("assigned_to")
        }

    # -----------------------------------
    # ✅ FINAL RESPONSE
    # -----------------------------------
    return {
        "status": final_status,   # 🔥 FIXED

        "claim_id": claim.get("claim_id"),

        # 🔹 CLAIM
        "claim": claim,

        # 🔹 VALIDATION
        "validation": {
            "valid": is_valid,
            "status": validation_status,
            "errors": errors
        },

        # 🔹 PIPELINE
        "pipeline": {
            "stage": pipeline.get("stage", "").upper(),
            "steps": steps
        },

        # 🔹 CASE
        "case": clean_case,

        # 🔹 FINANCIALS
        "financials": {
            "expected": reconciliation.get("expected"),
            "received": reconciliation.get("received"),
            "status": reconciliation.get("status", "").upper()
        },

        # 🔹 AI
        "ai": {
            "risk_score": denial_risk.get("risk_score"),
            "suggestion": denial_risk.get("suggestion")
        },

        # 🔹 WARNINGS
        "warnings": claim.get("warnings", [])
    }
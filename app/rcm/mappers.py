# app/rcm/mapper.py

def map_payload_to_claim(payload: dict) -> dict:
    """
    Converts flat CMS-1500 style payload into internal claim structure
    """

    claim = {
        "claim_id": payload.get("submission_id") or "AUTO-GEN-CLAIM",
        "patient": {
            "name": payload.get("pt_name"),
            "dob": f"{payload.get('birth_yy')}-{payload.get('birth_mm')}-{payload.get('birth_dd')}",
            "sex": payload.get("sex"),
            "address": {
                "street": payload.get("pt_street"),
                "city": payload.get("pt_city"),
                "state": payload.get("pt_state"),
                "zip": payload.get("pt_zip"),
            }
        },
        "provider": {
            "npi": payload.get("billing_provider_npi"),
            "name": payload.get("physician_signature"),
            "tax_id": payload.get("tax_id"),
        },
        "payer": {
            "name": payload.get("insurance_name"),
            "type": payload.get("payer_type"),
            "member_id": payload.get("insurance_id"),
        },
        "services": []
    }

    # --- CPT → services ---
    for i in range(1, 10):
        cpt = payload.get(f"cpt{i}")
        charge = payload.get(f"cpt{i}_charge")

        if not cpt:
            continue

        try:
            charge_amount = float(charge)
        except Exception:
            charge_amount = 0.0

        claim["services"].append({
            "line": i,
            "cpt": cpt,
            "charge_amount": charge_amount,
            "units": int(payload.get("units", 1))
        })

    return claim

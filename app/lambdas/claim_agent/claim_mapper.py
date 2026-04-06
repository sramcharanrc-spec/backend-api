import uuid


def map_s3_json_to_claim(raw_data: dict) -> dict:
    """
    Maps CMS1500-style JSON from S3 into
    the canonical claim schema required by EDI 837.
    """

    # -------------------------
    # Patient
    # -------------------------
    patient_name = raw_data.get("pt_name")
    if not patient_name:
        raise ValueError("pt_name missing in raw claim data")

    patient = {
        "name": patient_name,
        "dob": f"{raw_data.get('birth_yy')}-{raw_data.get('birth_mm')}-{raw_data.get('birth_dd')}",
        "gender": raw_data.get("sex"),
        "address": {
            "street": raw_data.get("pt_street"),
            "city": raw_data.get("pt_city"),
            "state": raw_data.get("pt_state"),
            "zip": raw_data.get("pt_zip"),
        },
    }

    # -------------------------
    # Provider
    # -------------------------
    provider = {
        "name": raw_data.get("service_facility_name"),
        "npi": raw_data.get("billing_provider_npi"),
        "phone": raw_data.get("billing_provider_phone"),
    }

    # -------------------------
    # Claim ID
    # -------------------------
    claim_id = raw_data.get(
        "claim_id",
        f"CLM-{uuid.uuid4().hex[:10]}"
    )

    # -------------------------
    # Services (EDI REQUIRED)
    # -------------------------
    services = []

    for i in range(1, 10):
        cpt = raw_data.get(f"cpt{i}")
        charge = raw_data.get(f"cpt{i}_charge")

        if cpt and float(charge or 0) > 0:
            services.append({
                "cpt": cpt,
                "charge": float(charge),
                "units": 1,
                "place_of_service": raw_data.get("place_of_service", "11"),
                "description": raw_data.get(f"cpt{i}_desc"),
            })

    if not services:
        raise ValueError("No billable services found in claim")

    # -------------------------
    # Final Canonical Claim
    # -------------------------
    claim = {
        "claim_id": claim_id,
        "patient": patient,
        "provider": provider,
        "payer": {
            "name": raw_data.get("insurance_name"),
            "type": raw_data.get("payer_type"),
            "policy_id": raw_data.get("insurance_id"),
        },
        "services": services,
        "total_charge": float(raw_data.get("total_charge", 0)),
        "source": "S3_GENERATED",
    }

    return claim

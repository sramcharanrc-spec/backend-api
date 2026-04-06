# import uuid
# from app.intake.service_extractor import extract_services


# def map_to_claim(extracted):

#     def get_field(keys, default=""):
#         for k in extracted.keys():
#             for key in keys:
#                 if key.lower() in k.lower():
#                     return extracted[k]
#         return default

#     # 🔥 Extract services separately
#     services = extract_services(extracted)

#     claim = {
#         "claim_id": f"CLM-{uuid.uuid4().hex[:10]}",

#         "patient": {
#             "name": get_field(["patient", "name"]),
#             "dob": get_field(["dob", "birth"])
#         },

#         "provider": {
#             "name": get_field(["provider"]),
#             "npi": get_field(["npi"])
#         },

#         "payer": {
#             "name": get_field(["insurance", "payer"])
#         },

#         # 🔥 Multi-line CPT support
#         "services": services if services else [],

#         # 🔥 Auto total from services
#         "total_charge": sum([s["charge"] for s in services]) if services else 0,

#         "source": "OCR_PIPELINE"
#     }

#     return claim

import uuid
from app.intake.service_extractor import extract_services


def map_to_claim(extracted):

    def get_exact(label):
        for k, v in extracted.items():
            if k.strip().lower() == label.lower():
                return v
        return ""

    def get_contains(keys, exclude=None):
        for k, v in extracted.items():
            key_lower = k.lower()

            if exclude and any(e in key_lower for e in exclude):
                continue

            if all(word in key_lower for word in keys):
                return v

        return ""

    # -------------------------
    # 🔥 FIXED FIELD EXTRACTION
    # -------------------------

    patient_name = get_contains(["name"], exclude=["provider", "hospital"])
    provider_name = get_contains(["provider"]) or get_contains(["name"], exclude=["patient"])

    # fallback if still wrong
    if not patient_name or patient_name == provider_name:
        patient_name = get_exact("Name:")  # fallback

    # -------------------------
    # Services
    # -------------------------
    services = extract_services(extracted)

    # -------------------------
    # CLAIM
    # -------------------------
    claim = {
        "claim_id": f"CLM-{uuid.uuid4().hex[:10]}",

        "patient": {
            "name": patient_name or "Unknown",
            "dob": get_contains(["dob"]) or get_contains(["birth"])
        },

        "provider": {
            "name": provider_name,
            "npi": get_contains(["npi"])
        },

        "payer": {
            "name": get_contains(["payer"]) or get_contains(["insurance"])
        },

        "services": services if services else [],

        "total_charge": sum([s["charge"] for s in services]) if services else 0,

        "source": "OCR_PIPELINE"
    }

    return claim
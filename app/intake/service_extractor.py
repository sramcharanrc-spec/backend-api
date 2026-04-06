import re


def extract_services(extracted):

    services = []

    # 🔥 Case 1: CPT in keys (your current case)
    for k, v in extracted.items():

        # Find CPT in key
        cpt_match = re.search(r"\b(\d{5})\b", k)

        # Find amount in value
        amount_match = re.search(r"\d+\.?\d*", str(v))

        if cpt_match and amount_match:
            services.append({
                "cpt": cpt_match.group(1),
                "charge": float(amount_match.group())
            })

    # 🔥 Case 2: fallback (full text scan)
    if not services:
        full_text = " ".join([str(v) for v in extracted.values()])

        matches = re.findall(
            r"(?:CPT[:\s]*)(\d{5}).*?(?:\$?)(\d+\.?\d*)",
            full_text,
            re.IGNORECASE
        )

        for m in matches:
            services.append({
                "cpt": m[0],
                "charge": float(m[1])
            })

    return services
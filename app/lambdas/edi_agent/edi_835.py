# app/rcm/edi_835.py

"""
Basic EDI 835 parser (production-safe starter)

This extracts:
- claim_id
- paid_amount
- adjustment reasons
"""

def parse_edi_835(edi_text: str) -> dict:
    """
    Very lightweight parser.
    Later you can replace this with full ANSI X12 parsing.
    """

    claim_id = None
    paid_amount = 0.0
    adjustments = []

    segments = edi_text.split("~")

    for segment in segments:
        elements = segment.split("*")
        tag = elements[0]

        # CLP = Claim Payment Information
        if tag == "CLP":
            # CLP*claim_id*status*total_charge*paid_amount*...
            claim_id = elements[1]
            try:
                paid_amount = float(elements[4])
            except (IndexError, ValueError):
                paid_amount = 0.0

        # CAS = Claim Adjustment
        if tag == "CAS":
            # CAS*group*code*amount*qty
            try:
                adjustments.append({
                    "group": elements[1],
                    "code": elements[2],
                    "amount": float(elements[3])
                })
            except (IndexError, ValueError):
                continue

    return {
        "claim_id": claim_id,
        "paid_amount": paid_amount,
        "adjustments": adjustments
    }

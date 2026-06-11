from __future__ import annotations


def parse_edi_835(edi_835: str) -> dict:
    text = edi_835 or ""
    segments = [segment for segment in text.replace("\n", "~").split("~") if segment]
    submission_id = None
    paid_amount = 0.0

    for segment in segments:
        parts = segment.split("*")
        if parts[0] in {"TRN", "CLP"} and len(parts) > 1:
            submission_id = submission_id or parts[-1]
        if parts[0] == "CLP" and len(parts) > 4:
            try:
                paid_amount = float(parts[4])
            except ValueError:
                paid_amount = 0.0

    return {
        "submission_id": submission_id or "UNKNOWN",
        "status": "PAID" if paid_amount > 0 else "RECEIVED",
        "paid_amount": paid_amount,
        "raw_edi": edi_835,
    }


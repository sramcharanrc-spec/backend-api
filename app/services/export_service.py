import json
import csv
import zipfile
from datetime import datetime
from app.services.audit_service import get_audit_logs
from app.services.pdf_service import generate_audit_pdf


def export_case_data(claim_id, record, format_type="json"):

    case = record.get("case")
    claim = record.get("claim")
    logs = get_audit_logs(claim_id)

    data = {
        "claim_id": claim_id,
        "claim": claim,
        "case": case,
        "audit_trail": logs,
        "exported_at": datetime.utcnow().isoformat()
    }

    # -------------------------
    # JSON EXPORT
    # -------------------------
    if format_type == "json":
        return data

    # -------------------------
    # CSV EXPORT
    # -------------------------
    elif format_type == "csv":
        file_path = f"/mnt/data/{claim_id}_audit.csv"

        with open(file_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)

        return {"file": file_path}

    # -------------------------
    # PDF EXPORT
    # -------------------------
    elif format_type == "pdf":
        pdf_path = generate_audit_pdf(claim_id, case, logs)
        return {"file": pdf_path}

    # -------------------------
    # ZIP EXPORT (🔥 BEST)
    # -------------------------
    elif format_type == "zip":
        zip_path = f"/mnt/data/{claim_id}_package.zip"

        pdf_path = generate_audit_pdf(claim_id, case, logs)

        json_path = f"/mnt/data/{claim_id}.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        with zipfile.ZipFile(zip_path, "w") as z:
            z.write(pdf_path)
            z.write(json_path)

        return {"file": zip_path}

    return {"error": "Invalid format"}

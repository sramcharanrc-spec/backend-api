from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.pagesizes import letter
import os
import hashlib
import json

from decimal import Decimal
from datetime import datetime

def json_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def generate_pdf_signature(data):

    payload = json.dumps(
        data,
        sort_keys=True,
        default=json_serializer   
    )

    return hashlib.sha256(payload.encode()).hexdigest()

def generate_audit_pdf(claim_id, case, logs):

    import os

    os.makedirs("exports", exist_ok=True)

    file_path = os.path.join("exports", f"{claim_id}_audit_report.pdf")

    # ✅ CREATE DOCUMENT (THIS WAS MISSING)
    doc = SimpleDocTemplate(file_path, pagesize=letter)

    styles = getSampleStyleSheet()

    content = []

    # -------------------------
    # 🏷 Title
    # -------------------------
    content.append(Paragraph(f"AUDIT REPORT - {claim_id}", styles["Title"]))
    content.append(Spacer(1, 12))

    content.append(Paragraph(f"Generated At: {datetime.utcnow()}", styles["Normal"]))
    content.append(Spacer(1, 12))

    # -------------------------
    # 📦 Case Section
    # -------------------------
    content.append(Paragraph("CASE DETAILS", styles["Heading2"]))
    content.append(Spacer(1, 8))

    if case:
        for key, value in case.items():
            content.append(Paragraph(f"<b>{key}:</b> {value}", styles["Normal"]))
            content.append(Spacer(1, 6))
    else:
        content.append(Paragraph("No case data available", styles["Normal"]))

    content.append(Spacer(1, 12))

    # -------------------------
    # 🔐 Audit Trail Table
    # -------------------------
    content.append(Paragraph("AUDIT TRAIL", styles["Heading2"]))
    content.append(Spacer(1, 8))

    if logs:
        table_data = [["Step", "Status", "Timestamp", "Hash"]]

        for log in logs:
            table_data.append([
                log.get("step"),
                log.get("status"),
                log.get("timestamp"),
                log.get("hash")  # short hash for readability
            ])

        table = Table(table_data, repeatRows=1)

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ]))

        content.append(table)
    else:
        content.append(Paragraph("No audit logs available", styles["Normal"]))

    content.append(Spacer(1, 12))

    # -------------------------
    # 🔍 Integrity Note
    # -------------------------
    content.append(Paragraph(
        "Integrity: This report includes tamper-proof audit logs secured using hash chaining.",
        styles["Italic"]
    ))


    # -------------------------
    # 🔒 Generate signature
    # -------------------------
    signature_payload = {
    "claim_id": claim_id,
    "case": case,
    "logs": logs
    }

    pdf_hash = generate_pdf_signature(signature_payload)

    content.append(Spacer(1, 12))
    content.append(Paragraph("DIGITAL SIGNATURE", styles["Heading2"]))
    content.append(Paragraph(pdf_hash, styles["Normal"]))

    # -------------------------
    # 🧾 Build PDF
    # -------------------------
    doc.build(content)

    print(f"📄 PDF Generated: {file_path}")

    return file_path


import json
import logging
import os
import uuid
import traceback
from io import BytesIO
from datetime import datetime
import time
from datetime import datetime, timedelta
from app.utils.security import mask_presigned_url, mask_sensitive_payload
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from app.intake.form_normalizer import fix_split_dates
from app.utils.security import mask_presigned_url
try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject
except ModuleNotFoundError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
        from PyPDF2.pdf_gen import NameObject, BooleanObject
    except (ModuleNotFoundError, ImportError):
        PdfReader = None
        PdfWriter = None
        NameObject = None
        BooleanObject = None

# ======================================================================
# AWS CLIENTS
# ======================================================================
logger = logging.getLogger(__name__)

load_dotenv()

s3 = boto3.client("s3")

# ======================================================================
# ENVIRONMENT VARIABLES (FROM YOUR ACTUAL SETUP)
# ======================================================================
# ======================================================================
# ENVIRONMENT VARIABLES
# ======================================================================

TEMPLATE_BUCKET = os.getenv(
    "TEMPLATE_BUCKET",
    ""
).strip()

TEMPLATE_KEY = os.getenv(
    "TEMPLATE_KEY",
    ""
).strip()

CLAIM_DATA_BUCKET = os.environ.get(
    "CLAIM_DATA_BUCKET",
    ""
).strip()

OUTPUT_BUCKET = os.getenv(
    "OUTPUT_BUCKET",
    ""
).strip()

FORM_OUTPUT_BUCKET = os.getenv(
    "FORM_OUTPUT_BUCKET",
    OUTPUT_BUCKET
).strip()

EDI_OUTPUT_BUCKET = os.getenv(
    "EDI_OUTPUT_BUCKET",
    ""
).strip()

logger.debug(
    "CMS1500 S3 configuration loaded: template_bucket=%s template_key_configured=%s output_bucket=%s",
    bool(TEMPLATE_BUCKET),
    bool(TEMPLATE_KEY),
    bool(FORM_OUTPUT_BUCKET),
)

DDB_TABLE = os.environ.get("DDB_TABLE")
if DDB_TABLE:
    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    table = dynamodb.Table(DDB_TABLE)
else:
    table = None
# ======================================================================
# CONSTANTS
# ======================================================================
TEXT_COLOR = (0, 0, 0)
TEXT_FONT_SIZE = 11
MAX_LINES = 6


class Cms1500TemplateUnavailable(RuntimeError):
    pass


def cms1500_template_unavailable_response(error=None):
    if error:
        logger.error("Template missing:%s", error)
    return {
        "status": "PARTIAL_SUCCESS",
        "route": "MANUAL_REVIEW",
        "reason": "CMS template unavailable",
        "message": "CMS template unavailable",
    }


def _load_template_object():
    try:
        s3.head_object(
            Bucket=TEMPLATE_BUCKET,
            Key=TEMPLATE_KEY
        )
        return s3.get_object(
            Bucket=TEMPLATE_BUCKET,
            Key=TEMPLATE_KEY
        )
    except (ClientError, BotoCoreError) as error:
        logger.error("Template missing:%s", error)
        raise Cms1500TemplateUnavailable("CMS template unavailable") from error
    except Exception as error:
        logger.error("Template missing:%s", error)
        raise Cms1500TemplateUnavailable("CMS template unavailable") from error


# ======================================================================
# BEDROCK RESPONSE FORMAT
# ======================================================================
def build_bedrock_response(action_group, function_name, api_path, http_method, body_dict):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function_name,
            "apiPath": api_path,
            "httpMethod": http_method,
            "responseBody": {
                "application/json": {
                    "body": body_dict
                }
            }
        }
    }


# ======================================================================
# PDF UTILITIES
# ======================================================================
def set_need_appearances(writer: PdfWriter):
    root = writer._root_object
    root.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    acroform = root.get("/AcroForm")
    if acroform:
        try:
            acroform = acroform.get_object()
        except AttributeError:
            pass
        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})


# ======================================================================
# DATA NORMALIZATION FOR PDF
# ======================================================================
def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _clean(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _first(*values, default=""):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def _address_street(patient: dict) -> str:
    address = patient.get("address", "")
    if isinstance(address, dict):
        return _clean(address.get("street") or address.get("line1") or address.get("address"))
    return _clean(address)


def _normalize_gender(value) -> str:
    raw = _clean(value).lower()
    if raw in ("m", "male"):
        return "M"
    if raw in ("f", "female"):
        return "F"
    return _clean(value)


def _split_iso_date(value):
    raw = _clean(fix_split_dates(value))
    parts = raw.split("/")
    if len(parts) == 3 and all(parts):
        return parts[0], parts[1], parts[2]
    parts = raw.split("-")
    if len(parts) == 3 and all(parts):
        return parts[1], parts[2], parts[0]
    return "", "", ""


def _claim_patient_id(claim_data: dict, fallback="unknown") -> str:
    patient = _as_dict(claim_data.get("patient"))
    return _clean(
        _first(
            claim_data.get("patient_id"),
            claim_data.get("patientId"),
            patient.get("id"),
            patient.get("patient_id"),
            claim_data.get("claim_id"),
            fallback,
        ),
        fallback,
    )


def prepare_pdf_data(data: dict) -> dict:
    mapped = {}

    patient = _as_dict(data.get("patient"))
    provider = _as_dict(data.get("provider"))
    insurance = _as_dict(data.get("insurance")) or _as_dict(data.get("payer"))
    claim = _as_dict(data.get("claim"))

    mapped["pt_name"] = _clean(_first(patient.get("name"), data.get("pt_name"), data.get("patient_name")))
    mapped["pt_dob"] = _clean(_first(patient.get("dob"), data.get("dob"), data.get("patient_dob")))
    mapped["sex"] = _normalize_gender(_first(patient.get("gender"), patient.get("sex"), data.get("sex")))
    mapped["insurance_id"] = _clean(
        _first(
            insurance.get("member_id"),
            insurance.get("policy_id"),
            insurance.get("id"),
            data.get("insurance_id"),
        )
    )
    mapped["pt_street"] = _clean(_first(_address_street(patient), data.get("pt_street")))
    mapped["pt_city"] = _clean(_first(patient.get("city"), _as_dict(patient.get("address")).get("city"), data.get("pt_city")))
    mapped["pt_state"] = _clean(_first(patient.get("state"), _as_dict(patient.get("address")).get("state"), data.get("pt_state")))
    mapped["pt_zip"] = _clean(_first(patient.get("zip"), _as_dict(patient.get("address")).get("zip"), data.get("pt_zip")))
    mapped["provider_name"] = _clean(_first(provider.get("name"), data.get("provider_name"), data.get("physician_signature")))
    mapped["npi"] = _clean(_first(provider.get("npi"), data.get("npi"), data.get("billing_provider_npi")))
    mapped["billing_provider_npi"] = mapped["npi"]
    mapped["diagnosis_pointer"] = _clean(
        _first(
            claim.get("diagnosis_code"),
            claim.get("diagnosis_pointer"),
            data.get("diagnosis_code"),
            data.get("diagnosis_pointer"),
            data.get("diagnosis1"),
            default="",
        )
    )
    mapped["diagnosis1"] = mapped["diagnosis_pointer"]

    birth_mm, birth_dd, birth_yy = _split_iso_date(mapped["pt_dob"])
    mapped["birth_mm"] = _clean(_first(data.get("birth_mm"), birth_mm))
    mapped["birth_dd"] = _clean(_first(data.get("birth_dd"), birth_dd))
    mapped["birth_yy"] = _clean(_first(data.get("birth_yy"), birth_yy))

    services = claim.get("services") or data.get("services") or []
    if isinstance(services, dict):
        services = [services]
    if not isinstance(services, list):
        services = []

    for i, svc in enumerate(services[:MAX_LINES], start=1):
        svc = _as_dict(svc)
        mapped[f"cpt{i}"] = _clean(svc.get("cpt"))
        mapped[f"ch{i}"] = _clean(_first(svc.get("charge"), svc.get("charge_amount")))
        mapped[f"day{i}"] = _clean(svc.get("units"))

    for i in range(1, MAX_LINES + 1):
        mapped[f"cpt{i}"] = _clean(_first(mapped.get(f"cpt{i}"), data.get(f"cpt{i}")))
        mapped[f"ch{i}"] = _clean(_first(mapped.get(f"ch{i}"), data.get(f"ch{i}"), data.get(f"cpt{i}_charge")))
        mapped[f"day{i}"] = _clean(_first(mapped.get(f"day{i}"), data.get(f"day{i}"), data.get(f"units_{i}"), data.get("units")))
        mapped[f"cpt{i}_charge"] = mapped[f"ch{i}"]
        mapped[f"units_{i}"] = mapped[f"day{i}"]

    mapped["t_charge"] = _clean(
        _first(
            claim.get("total_charge"),
            data.get("total_charge"),
            data.get("t_charge"),
            default="0.00",
        )
    )
    mapped["total_charge"] = mapped["t_charge"]

    # Preserve existing flat CMS-1500 values used by older pipeline callers.
    for key, value in data.items():
        if key not in mapped:
            mapped[key] = value

    mapped["rel_to_ins"] = _clean(mapped.get("rel_to_ins", "self")).lower()
    mapped["tax_id_type"] = _clean(mapped.get("tax_id_type", "EIN")).upper()

    return mapped


def build_cms1500_pdf_fields(claim_data: dict) -> dict:
    claim = _as_dict(claim_data.get("claim")) or claim_data
    patient = _as_dict(claim.get("patient") or claim_data.get("patient"))
    insurance = _as_dict(
        claim.get("insurance")
        or claim.get("payer")
        or claim_data.get("insurance")
        or claim_data.get("payer")
    )
    provider = _as_dict(claim.get("provider") or claim_data.get("provider"))
    services = claim.get("services") or claim_data.get("services") or []
    if isinstance(services, dict):
        services = [services]
    if not isinstance(services, list):
        services = []
    first_service = _as_dict(services[0]) if services else {}

    pdf_fields = {
        "patient_name": patient.get("name", ""),
        "patient_dob": patient.get("dob", ""),
        "patient_gender": patient.get("gender", ""),
        "insurance_id": insurance.get("member_id", ""),
        "address": _address_street(patient),
        "city": patient.get("city", ""),
        "state": patient.get("state", ""),
        "zip": patient.get("zip", ""),
        "provider_npi": provider.get("npi", ""),
        "diagnosis": claim.get("diagnosis_code", ""),
        "cpt1": first_service.get("cpt", ""),
        "charge1": _first(first_service.get("charge"), first_service.get("charge_amount")),
    }

    prepared = prepare_pdf_data(claim_data)
    pdf_fields.update({
        "pt_name": pdf_fields["patient_name"] or prepared.get("pt_name", ""),
        "pt_dob": pdf_fields["patient_dob"] or prepared.get("pt_dob", ""),
        "sex": _normalize_gender(pdf_fields["patient_gender"] or prepared.get("sex", "")),
        "pt_street": pdf_fields["address"] or prepared.get("pt_street", ""),
        "pt_city": pdf_fields["city"] or prepared.get("pt_city", ""),
        "pt_state": pdf_fields["state"] or prepared.get("pt_state", ""),
        "pt_zip": pdf_fields["zip"] or prepared.get("pt_zip", ""),
        "npi": pdf_fields["provider_npi"] or prepared.get("npi", ""),
        "billing_provider_npi": pdf_fields["provider_npi"] or prepared.get("billing_provider_npi", ""),
        "diagnosis1": pdf_fields["diagnosis"] or prepared.get("diagnosis1", ""),
        "diagnosis_pointer": pdf_fields["diagnosis"] or prepared.get("diagnosis_pointer", ""),
        "ch1": pdf_fields["charge1"] or prepared.get("ch1", ""),
        "cpt1_charge": pdf_fields["charge1"] or prepared.get("cpt1_charge", ""),
        "t_charge": prepared.get("t_charge", ""),
        "total_charge": prepared.get("total_charge", ""),
        "birth_mm": prepared.get("birth_mm", ""),
        "birth_dd": prepared.get("birth_dd", ""),
        "birth_yy": prepared.get("birth_yy", ""),
    })

    for index in range(1, MAX_LINES + 1):
        pdf_fields.setdefault(f"cpt{index}", prepared.get(f"cpt{index}", ""))
        pdf_fields.setdefault(f"ch{index}", prepared.get(f"ch{index}", ""))
        pdf_fields.setdefault(f"day{index}", prepared.get(f"day{index}", ""))
        pdf_fields.setdefault(f"cpt{index}_charge", prepared.get(f"cpt{index}_charge", ""))
        pdf_fields.setdefault(f"units_{index}", prepared.get(f"units_{index}", ""))

    return {key: _clean(value) for key, value in pdf_fields.items()}


def generate_cms1500_pdf_bytes(claim_data: dict) -> tuple[bytes, int]:
    template_obj = _load_template_object()

    template_pdf = BytesIO(
        template_obj["Body"].read()
    )

    reader = PdfReader(
        template_pdf
    )

    writer = PdfWriter()

    root = reader.trailer.get("/Root", {})
    if "/AcroForm" in root:
        writer._root_object.update({
            NameObject("/AcroForm"): root["/AcroForm"]
        })

    for page in reader.pages:
        writer.add_page(page)

    pdf_fields = build_cms1500_pdf_fields(claim_data)

    for page in writer.pages:
        writer.update_page_form_field_values(
            page,
            pdf_fields
        )

    writer._root_object.update({
        NameObject(
            "/NeedAppearances"
        ):
        BooleanObject(
            True
        )
    })
    set_need_appearances(writer)

    template_fields = reader.get_fields() or {}
    fields_filled = sum(
        1
        for name, value in pdf_fields.items()
        if name in template_fields and _clean(value)
    )

    buffer = BytesIO()

    writer.write(
        buffer
    )

    buffer.seek(
        0
    )

    return buffer.getvalue(), fields_filled


def store_cms1500_pdf(pdf_bytes: bytes, patient_id: str) -> tuple[str, str]:
    out_key = f"forms/{patient_id}/CMS1500_{uuid.uuid4()}.pdf"

    s3.put_object(
        Bucket=FORM_OUTPUT_BUCKET,
        Key=out_key,
        Body=pdf_bytes,
        ContentType="application/pdf"
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": FORM_OUTPUT_BUCKET,
            "Key": out_key
        }
    )

    return out_key, url


# ======================================================================
# FILL PDF FIELDS
# ======================================================================
def fill_pdf_fields(reader: PdfReader, writer: PdfWriter, data: dict):
    fields = reader.get_fields() or {}
    pdf_values = {name: str(data[name]) for name in fields if name in data}
    missing = sorted(set(data.keys()) - set(fields.keys()))
    for page in writer.pages:
        writer.update_page_form_field_values(page, pdf_values)
    print(
        f"CMS1500 field population: template_fields={len(fields)}, "
        f"fields_filled={len(pdf_values)}, missing_mapped_fields={len(missing)}"
    )
    return len(pdf_values)


# ======================================================================
# FORM PROCESSING (PURE BUSINESS LOGIC)
# ======================================================================
def process_form(claim_data, patient_id,sessionid):
    patient_id = _claim_patient_id(claim_data, patient_id)

    if PdfReader is None or PdfWriter is None:
        return {
            "status": "skipped",
            "message": "pypdf is not installed; CMS1500 PDF generation skipped",
        }

    if not all([TEMPLATE_BUCKET, TEMPLATE_KEY, FORM_OUTPUT_BUCKET]):
        return {
            "status": "skipped",
            "message": "CMS1500 template/output S3 environment variables are not configured",
        }

    try:
        final_pdf, filled_count = generate_cms1500_pdf_bytes(claim_data)
    except Cms1500TemplateUnavailable as error:
        try:
            update_job(sessionid, progress="PDF", status="PDF_FAILED")
        except Exception as job_error:
            logger.warning("Failed updating CMS1500 job after template miss: %s", job_error)
        return cms1500_template_unavailable_response(error)

    print(f"CMS1500 PDF generated: size={len(final_pdf)} bytes, fields_filled={filled_count}")

    print("STORING CMS1500 PDF IN S3")
    out_key, url = store_cms1500_pdf(final_pdf, patient_id)
    print(f"CMS1500 PDF uploaded: s3://{FORM_OUTPUT_BUCKET}/{out_key}")
    update_job(sessionid, progress="PDF",status="PDF_SUCCESS")

    return {
        "status": "success",
        "message": f"CMS1500 generated for {patient_id}",
        "file_key": out_key,
        "file_url": url,
        "fields_filled": filled_count,
    }

# ======================================================================
# EDI HELPERS (SAME LOGIC AS YOUR OLD 837 LAMBDA)
# ======================================================================
def seg(*elements):
    return "*".join([x if x else "" for x in elements]) + "~"


def build_837P(claim):
    edi = []
    now = datetime.utcnow()

    edi.append(seg(
        "ISA", "00", "", "00", "",
        "ZZ", "SENDERID", "ZZ", "RECEIVERID",
        now.strftime("%y%m%d"), now.strftime("%H%M"),
        "U", "00401", "000000001", "0", "P", ":"
    ))

    edi.append(seg(
        "GS", "HC", "SENDERID", "RECEIVERID",
        now.strftime("%Y%m%d"), now.strftime("%H%M"),
        "1", "X", "005010X222A1"
    ))

    edi.append(seg("ST", "837", "0001"))
    edi.append(seg(
        "BHT", "0019", "00", "CLM" + now.strftime("%H%M%S"),
        now.strftime("%Y%m%d"), "CH"
    ))

    full = claim.get("pt_name", "")
    first = full.split(" ")[0] if full else ""
    last = " ".join(full.split(" ")[1:]) if full else ""

    edi.append(seg("NM1", "IL", "1", last, first, "", "", "MI",
                   claim.get("insurance_id", "UNKNOWN")))
    edi.append(seg("N3", claim.get("pt_street", "")))
    edi.append(seg("N4", claim.get("pt_city", ""), claim.get("pt_state", ""), claim.get("pt_zip", "")))

    edi.append(seg("HI", f"ABK:{claim.get('diagnosis_pointer','1')}"))

    edi.append(seg(
        "CLM",
        claim.get("pt_name", "").replace(" ", ""),
        claim.get("total_charge", "0.00"),
        "", "", "11:B:1"
    ))

    start = f"{claim['service_from_yy']}{claim['service_from_mm']}{claim['service_from_dd']}"
    end = f"{claim['service_to_yy']}{claim['service_to_mm']}{claim['service_to_dd']}"
    edi.append(seg("DTP", "472", "RD8", start + "-" + end))

    edi.append(seg("SE", str(len(edi) + 1), "0001"))
    edi.append(seg("GE", "1", "1"))
    edi.append(seg("IEA", "1", "000000001"))

    return "\n".join(edi)


def build_837I(claim):
    edi = []
    now = datetime.utcnow()

    edi.append(seg(
        "ISA", "00", "", "00", "",
        "ZZ", "SENDERID", "ZZ", "RECEIVERID",
        now.strftime("%y%m%d"), now.strftime("%H%M"),
        "U", "00401", "000000001", "0", "P", ":"
    ))

    edi.append(seg(
        "GS", "HC", "SENDERID", "RECEIVERID",
        now.strftime("%Y%m%d"), now.strftime("%H%M"),
        "1", "X", "005010X223A2"
    ))

    edi.append(seg("ST", "837", "0001"))
    edi.append(seg(
        "BHT", "0019", "00", "CLM" + now.strftime("%H%M%S"),
        now.strftime("%Y%m%d"), "CH"
    ))

    full = claim.get("pt_name", "")
    first = full.split(" ")[0] if full else ""
    last = " ".join(full.split(" ")[1:]) if full else ""

    edi.append(seg("NM1", "IL", "1", last, first, "", "", "MI",
                   claim.get("insurance_id", "UNKNOWN")))

    start = f"{claim['service_from_yy']}{claim['service_from_mm']}{claim['service_from_dd']}"
    end = f"{claim['service_to_yy']}{claim['service_to_mm']}{claim['service_to_dd']}"

    edi.append(seg("DTP", "434", "D8", start))
    edi.append(seg("DTP", "435", "D8", end))

    edi.append(seg(
        "CLM",
        claim.get("pt_name", "").replace(" ", ""),
        claim.get("total_charge", "0.00"),
        "", "",
        "11:A:1"
    ))

    edi.append(seg("SE", str(len(edi) + 1), "0001"))
    edi.append(seg("GE", "1", "1"))
    edi.append(seg("IEA", "1", "000000001"))

    return "\n".join(edi)


def process_edi(claim, patient_id,sessionid,validated_s3_key=None):
    if not EDI_OUTPUT_BUCKET:
        return {
            "status": "skipped",
            "message": "EDI_OUTPUT_BUCKET is not configured",
        }

    encounter = claim.get("encounter_type", "").lower()

    if encounter == "outpatient":
        edi_text = build_837P(claim)
        suffix = "837P"
    elif encounter == "inpatient":
        edi_text = build_837I(claim)
        suffix = "837I"
    else:
        return {
            "status": "error",
            "message": "Invalid encounter_type"
        }

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    edi_key = f"edi/{patient_id}/{patient_id}_{timestamp}_{suffix}.edi"

    s3.put_object(
        Bucket=EDI_OUTPUT_BUCKET,
        Key=edi_key,
        Body=edi_text.encode("utf-8"),
        ContentType="text/plain"
    )
    update_job(sessionid, progress="EDI",status="SUCCESS")
    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": EDI_OUTPUT_BUCKET, "Key": edi_key},
        ExpiresIn=3600
    )

    resp = {
        "status": "success",
        "patient_id": patient_id,
        "edi_key": edi_key,
        "download_url": presigned_url
    }
    if validated_s3_key:
        resp["validated_s3_key"] = validated_s3_key

    return resp

# def update_job(jobId, progress,status):
#     if not table or not jobId:
#         return False

#     ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
#     now = ist_now.strftime("%Y-%m-%d %H:%M:%S")

#     table.update_item(
#         Key={"jobId": jobId},
#         UpdateExpression="SET #progress = :p, #ts = :t, #st = :s",
#         ExpressionAttributeNames={
#             "#progress": "progress",
#             "#ts": "updatedAt",
#             "#st":"status"
#         },
#         ExpressionAttributeValues={
#             ":p": progress,
#             ":t": now,
#             ":s":status
#         },
#         ConditionExpression="attribute_exists(jobId)"
#     )
#     print("CMS1500 presigned URL generated")
#     return True

def update_job(jobId, progress=None, status=None):

    if not jobId:
        print("No jobId provided")
        return

    try:

        table.update_item(
            Key={
                "jobId": jobId
            },

            UpdateExpression=
            "SET #p=:p,#s=:s",

            ExpressionAttributeNames={
                "#p":"progress",
                "#s":"status"
            },

            ExpressionAttributeValues={
                ":p":progress or "",
                ":s":status or ""
            },

            ReturnValues="UPDATED_NEW"
        )

        print(
            f"Updated job {jobId}"
        )

    except Exception as e:

        print(
            f"Update failed: {e}"
        )

        try:

            table.put_item(
                Item={
                    "jobId":jobId,
                    "progress":progress or "",
                    "status":status or "",
                    "created_at":
                    datetime.utcnow().isoformat()
                }
            )

            print(
                f"Created missing job {jobId}"
            )

        except Exception as create_error:

            print(
                f"Create failed: {create_error}"
            )

# ======================================================================
# COMBINED BUSINESS HANDLER (FORM + EDI)
# ======================================================================
def generate_outputs(claim_data, patient_id, sessionid,validated_s3_key=None, mode="both"):
    """
    mode: "form", "edi", or "both"
    """
    from app.services.edi_service import process_edi as build_edi_output

    results = {}

    if mode in ("form", "both"):
        results["form"] = process_form(claim_data, patient_id,sessionid)
        time.sleep(1)
        
    if mode in ("edi", "both"):
        time.sleep(1)
        results["edi"] = build_edi_output(claim_data, patient_id, sessionid, validated_s3_key)

    return results


def extract_patient_id(event):
    """
    Extract patient_id from Bedrock Agent action group event
    """
    try:
        props = (
            event.get("requestBody", {})
                 .get("content", {})
                 .get("application/json", {})
                 .get("properties", [])
        )

        for p in props:
            if p.get("name") == "patient_id":
                return p.get("value")

    except Exception as e:
        print("Error extracting patient_id:", e)

    return None

def lambda_handler(event, context):
    print("Incoming event:", json.dumps(event))

    try:
        # -------------------------------------------------
        # STEP 0: Detect Bedrock request
        # -------------------------------------------------
        is_bedrock = False
        params = {}
        validated_s3_key = None
        patient_id = "unknown"
        mode = "both"

        try:
            body = event.get("requestBody", {})
            content = body.get("content", {})
            app_json = content.get("application/json", {})

            if "properties" in app_json:
                is_bedrock = True
                props = app_json["properties"]
                params = {item["name"]: item["value"] for item in props}
        except Exception:
            pass

        # -------------------------------------------------
        # STEP 1: Extract payload (common)
        # -------------------------------------------------
        if is_bedrock:
            validated_s3_key = params.get("validated_s3_key") or params.get("validated_claim_data")
            print("Vlaidated s3 key==>",validated_s3_key)
            mode = params.get("mode", "both")

            if not validated_s3_key:
                return build_bedrock_response(
                    event["actionGroup"],
                    event.get("function", "createFormAndEdi"),
                    event.get("apiPath"),
                    event.get("httpMethod"),
                    {"status": "error", "message": "validated_s3_key required"}
                )
            print("Reading from the S3by bedrock input")
            obj = s3.get_object(Bucket=CLAIM_DATA_BUCKET, Key=validated_s3_key)
            claim_data = json.loads(obj["Body"].read())

        else:
            if "body" in event:
                payload = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
                claim_data = payload
            else:
                claim_data = event

        # -------------------------------------------------
        # STEP 2: Encounter-based routing (CRITICAL)
        # -------------------------------------------------
        print("CLAIM DATA VALIDATED ==>", claim_data)
        encounter_type = claim_data.get("encounter_type")
        if not encounter_type:
            raise ValueError("encounter_type is required")

        encounter_type = encounter_type.lower()
        sessionid = event.get("sessionId")

        # -------------------------------------------------
        # INPATIENT → INVOKE UB-04 LAMBDA
        # -------------------------------------------------
        if encounter_type == "inpatient":
            print("Routing to UB-04 lambda")

            lambda_client = boto3.client("lambda")

            # -------------------------------------------------
            # BUILD PAYLOAD FOR UB-04
            # -------------------------------------------------
            if is_bedrock:
                # Forward Bedrock-style payload
                print("Inside the  bedrock if 1st:")
                ub04_payload = {
                    "patientId": extract_patient_id(event) ,
                    "data": claim_data,
                    "sessionId":event.get("sessionId"),
                    "mode":"both"
                }
            else:
                # Normal invocation (API / direct)
                ub04_payload = {
                    **claim_data,
                    "validated_s3_key": validated_s3_key,
                    "mode": mode,
                    "sessionId": event.get("sessionId")
                }

            # -------------------------------------------------
            # INVOKE UB-04 LAMBDA
            # -------------------------------------------------
            print("ub04_payload==>",ub04_payload)
            ub04_resp = lambda_client.invoke(
                FunctionName="ai-bot-tenders-ub-04-form-fun",
                InvocationType="RequestResponse",
                Payload=json.dumps(ub04_payload).encode("utf-8")
            )
            # print("FROM UB-04 FUNION : ",ub04_resp)
            
            raw = ub04_resp["Payload"].read().decode("utf-8")
            print("RAW ==>",raw)
            ub04_result = json.loads(raw)

            parsed_body = json.loads(ub04_result.get("body", "{}"))
            form_status = parsed_body.get("form", {}).get("status", "unknown")
            edi_status = parsed_body.get("edi", {}).get("status", "unknown")

            print("form_status , edi_status",form_status,edi_status )
            if form_status == "success":
                update_job(sessionid, progress="PDF",status="PDF_SUCCESS")
            if edi_status == "success":
                update_job(sessionid, progress="EDI",status="SUCCESS")


            # Unwrap API Gateway style body if present
            if isinstance(ub04_result, dict) and "body" in ub04_result:
                try:
                    ub04_result = json.loads(ub04_result["body"])
                except Exception:
                    pass

            # -------------------------------------------------
            # RETURN BACK TO BEDROCK
            # -------------------------------------------------
            if is_bedrock:
                return build_bedrock_response(
                    event["actionGroup"],
                    event.get("function", "createFormAndEdi"),
                    event.get("apiPath"),
                    event.get("httpMethod"),
                    {
                        "status": "success",
                        "encounter_type": "inpatient",
                        "form_type": "UB-04",
                        "patient_id": claim_data.get("patient_id"),
                        "validated_s3_key": validated_s3_key,
                        "result": ub04_result
                    }
                )

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "form_type": "UB-04",
                    "result": ub04_result
                })
            }


        # -------------------------------------------------
        # OUTPATIENT → CONTINUE CMS-1500 NORMAL FLOW
        # -------------------------------------------------
        if encounter_type.lower() != "outpatient":
            raise ValueError(f"Unsupported encounter_type: {encounter_type}")

        patient_id = extract_patient_id(event)

        results = generate_outputs(
            claim_data,
            patient_id,
            sessionid,
            validated_s3_key,
            mode
        )

        # -------------------------------------------------
        # STEP 3: Return CMS-1500 response
        # -------------------------------------------------
        if is_bedrock:
            return build_bedrock_response(
                event["actionGroup"],
                event.get("function", "createFormAndEdi"),
                event.get("apiPath"),
                event.get("httpMethod"),
                results
            )

        return {
            "statusCode": 200,
            "body": json.dumps(results)
        }

    except Exception as e:
        traceback.print_exc()

        if "requestBody" in event:
            return build_bedrock_response(
                event.get("actionGroup", "UnknownActionGroup"),
                event.get("function", "createFormAndEdi"),
                event.get("apiPath"),
                event.get("httpMethod", "POST"),
                {"status": "error", "message": str(e)}
            )

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

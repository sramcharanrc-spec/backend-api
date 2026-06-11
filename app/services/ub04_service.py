import json
import os
import uuid
import traceback
from io import BytesIO
import time
from datetime import datetime, timedelta
import boto3
from dotenv import load_dotenv
try:
    import fitz
except ModuleNotFoundError:
    fitz = None

# ======================================================================
# AWS CLIENTS
# ======================================================================
load_dotenv()

s3 = boto3.client("s3")

# ======================================================================
# ENVIRONMENT VARIABLES
# ======================================================================
SOURCE_BUCKET = os.getenv("SOURCE_BUCKET", "")
SOURCE_KEY = os.getenv("SOURCE_KEY", "")
DEST_BUCKET = os.getenv("DEST_BUCKET", os.getenv("OUTPUT_BUCKET", ""))
CLAIM_DATA_BUCKET = os.getenv("CLAIM_DATA_BUCKET", "")
EDI_OUTPUT_BUCKET = os.getenv("EDI_OUTPUT_BUCKET", "")
DDB_TABLE = os.environ.get('DDB_TABLE')

if DDB_TABLE:
    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    table = dynamodb.Table(DDB_TABLE)
else:
    table = None

# ======================================================================
# HELPER FUNCTIONS
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

def update_job(jobId, progress, status):
    """Update job status in DynamoDB"""
    if not table:
        return False
    try:
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        now = ist_now.strftime("%Y-%m-%d %H:%M:%S")
        table.update_item(
            Key={"jobId": jobId},
            UpdateExpression="SET #progress = :p, #ts = :t, #st = :s",
            ExpressionAttributeNames={
                "#progress": "progress",
                "#ts": "updatedAt",
                "#st": "status"
            },
            ExpressionAttributeValues={
                ":p": progress,
                ":t": now,
                ":s": status
            }
        )
        return True
    except Exception as e:
        print(f"ERROR updating job: {str(e)}")
        return False

# ======================================================================
# PDF GENERATION FUNCTIONS
# ======================================================================
def flatten_pdf(pdf_bytes: bytes) -> bytes:
    """Flatten PDF by drawing field values and removing widgets"""
    if fitz is None:
        return pdf_bytes

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page in doc:
            widgets = page.widgets()
            if not widgets:
                continue
            
            for widget in widgets:
                value = widget.field_value
                
                if value:
                    rect = widget.rect
                    
                    if "remarks" in str(widget.field_name).lower():
                        fontsize = 7
                        if len(value) > 80:
                            value = value[:77] + "..."
                    else:
                        fontsize = 9
                    
                    text_y = rect.y0 + (rect.height * 0.8)
                    
                    try:
                        page.insert_text(
                            (rect.x0, text_y),
                            str(value),
                            fontsize=fontsize,
                            color=(0, 0, 0),
                            fontname="helvetica"
                        )
                    except:
                        pass
                
                try:
                    page.delete_widget(widget)
                except:
                    pass
        
        flattened_bytes = doc.write()
        doc.close()
        return flattened_bytes
    except Exception as e:
        print(f"ERROR in flatten_pdf: {str(e)}")
        return pdf_bytes

def fill_field(widget_dict, field_name, value, fields_filled):
    """
    Safe, non-recursive field filler.
    Returns (fields_filled, filled_bool)
    """

    if value is None:
        return fields_filled, False

    value_str = str(value).strip()
    if not value_str:
        return fields_filled, False

    widget = None

    # 1️⃣ Exact match
    if field_name in widget_dict:
        widget = widget_dict[field_name]
    else:
        # 2️⃣ Case-insensitive match (ONE PASS)
        lname = field_name.lower()
        for k, w in widget_dict.items():
            if k.lower() == lname:
                widget = w
                break

    if not widget:
        print(f"⚠ Field '{field_name}' not found")
        return fields_filled, False

    try:
        # Font sizing
        widget.text_fontsize = 7 if "remarks" in widget.field_name.lower() else 9
        widget.text_color = (0, 0, 0)
        widget.fill_color = (1, 1, 1)
        widget.text_font = "Helvetica"

        widget.field_value = value_str
        widget.update()

        return fields_filled + 1, True

    except Exception as e:
        print(f"❌ Failed to fill '{widget.field_name}': {e}")
        return fields_filled, False


def prepare_ub04_data(data: dict) -> dict:
    """Prepare data for UB-04 form"""
    mapped = dict(data)
    
    # Sex mapping
    sex = str(mapped.get("sex", "")).upper()
    mapped["sex_code"] = "2" if sex == "F" else "1"
    
    # Relationship code
    rel = str(mapped.get("rel_to_ins", "")).lower()
    if rel == "spouse":
        mapped["rel_code"] = "01"
    elif rel == "child":
        mapped["rel_code"] = "19"
    else:
        mapped["rel_code"] = "18"  # Self
    
    # Dates
    service_from = f"{mapped.get('service_from_mm', '01')}/{mapped.get('service_from_dd', '01')}/{mapped.get('service_from_yy', '2023')}"
    service_to = f"{mapped.get('service_to_mm', '01')}/{mapped.get('service_to_dd', '01')}/{mapped.get('service_to_yy', '2023')}"
    mapped["service_from_formatted"] = service_from
    mapped["service_to_formatted"] = service_to
    
    # Use single date if from and to are same
    if service_from == service_to:
        mapped["service_date"] = service_from
    else:
        mapped["service_date"] = f"{service_from} - {service_to}"
    
    # Birth date
    birthdate = f"{mapped.get('birth_mm', '01')}/{mapped.get('birth_dd', '01')}/{mapped.get('birth_yy', '1970')}"
    mapped["birthdate_formatted"] = birthdate
    
    # Addresses
    mapped["patient_address"] = f"{mapped.get('pt_street', '')}, {mapped.get('pt_city', '')} {mapped.get('pt_state', '')} {mapped.get('pt_zip', '')}"
    mapped["facility_address"] = f"{mapped.get('service_facility_address', '')}, {mapped.get('service_facility_city', '')} {mapped.get('service_facility_state', '')} {mapped.get('service_facility_zip', '')}"
    
    # Patient control number
    patient_name = mapped.get("pt_name", "Unknown")
    mapped["patient_control_number"] = f"PT{patient_name[:3].upper() if patient_name else 'UNK'}{datetime.now().strftime('%m%d')}"
    
    # Accept assignment
    accept_assignment = str(mapped.get("accept_assignment", "N")).upper()
    mapped["accept_assignment_code"] = "Y" if accept_assignment in ("Y", "YES", "TRUE", "1") else "N"
    
    # Collect CPT codes
    cpt_codes = []
    for i in range(1, 25):
        cpt_key = f"cpt{i}"
        cpt_desc_key = f"cpt{i}_desc"
        cpt_charge_key = f"cpt{i}_charge"
        
        if mapped.get(cpt_key) and str(mapped[cpt_key]).strip():
            cpt_codes.append({
                "code": mapped[cpt_key],
                "desc": mapped.get(cpt_desc_key, f"Service {i}"),
                "charge": mapped.get(cpt_charge_key, "0.00"),
                "index": i
            })
    
    mapped["cpt_codes"] = cpt_codes
    
    # Revenue codes mapping
    for cpt in cpt_codes:
        desc_upper = cpt["desc"].upper()
        rev_code = "300"  # Default lab
        
        if any(x in desc_upper for x in ["CT", "XRAY", "RADIOLOGY", "MRI", "SCAN", "DENSITY", "KNEES", "BONE"]):
            rev_code = "320"  # Radiology
        elif any(x in desc_upper for x in ["BATH", "THERAPY", "THERAPEUTIC", "PHYSICAL", "CONTRAST"]):
            rev_code = "420"  # Physical Therapy
        elif any(x in desc_upper for x in ["ASSAY", "TEST", "GLUCOSE", "BLOOD", "LAB", "BREATH"]):
            rev_code = "310"  # Clinical Lab
        elif any(x in desc_upper for x in ["VOLUME", "BLOOD", "TRANSFUSION", "AUTOLOGOUS"]):
            rev_code = "380"  # Blood
        elif any(x in desc_upper for x in ["URINE", "KIDNEY", "URETERAL", "RENAL", "FUNCTION"]):
            rev_code = "400"  # Renal
        elif any(x in desc_upper for x in ["THERAPEUTIC", "ACTIVITIES"]):
            rev_code = "420"  # Physical Therapy
        
        cpt["rev_code"] = rev_code
    
    return mapped

def generate_ub04_form(claim_data, patient_id, sessionid):
    """Generate UB-04 form"""
    print(f"Generating UB-04 form for patient: {patient_id}")

    if fitz is None:
        return {
            "status": "skipped",
            "message": "PyMuPDF is not installed; UB-04 PDF generation skipped",
        }
    
    if not all([SOURCE_BUCKET, SOURCE_KEY, DEST_BUCKET]):
        return {
            "status": "error",
            "message": "Missing required environment variables"
        }
    
    # Prepare data
    pdf_data = prepare_ub04_data(claim_data)
    fields_filled = 0
    
    try:
        # Load PDF template
        print(f"Loading template from: {SOURCE_BUCKET}/{SOURCE_KEY}")
        template = s3.get_object(Bucket=SOURCE_BUCKET, Key=SOURCE_KEY)
        pdf_bytes = template["Body"].read()
        print(f"UB-04 template loaded: s3://{SOURCE_BUCKET}/{SOURCE_KEY}, size={len(pdf_bytes)} bytes")
        
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Get all widgets
        widget_dict = {}
        for page in pdf:
            widgets = page.widgets()
            if not widgets:
                continue
            for widget in widgets:
                if widget.field_name:
                    widget_dict[widget.field_name] = widget
        
        print(f"Found {len(widget_dict)} form fields in template")
        
        # Debug: Print all field names
        print("=== Available Field Names ===")
        for field_name in sorted(widget_dict.keys())[:50]:  # First 50
            print(f"  {field_name}")
        
        print("\n=== Filling UB-04 Form Fields ===")
        
        # Fill Provider Information (Locator 1)
        fields_filled, _ = fill_field(widget_dict, "one", pdf_data.get("service_facility_name", ""), fields_filled)
        
        # Fill Provider Address (Locator 2)
        fields_filled, _ = fill_field(widget_dict, "two", pdf_data.get("facility_address", ""), fields_filled)
        
        # Patient Control Number (Locator 3a)
        fields_filled, _ = fill_field(widget_dict, "patctrl.0", pdf_data.get("patient_control_number", ""), fields_filled)
        
        # Type of Bill (Locator 4) - Usually "131" for outpatient
        fields_filled, _ = fill_field(widget_dict, "type", "131", fields_filled)
        
        # Federal Tax ID (Locator 5)
        fields_filled, _ = fill_field(widget_dict, "fedtax", pdf_data.get("tax_id", ""), fields_filled)
        
        # Statement Dates (Locator 6)
        fields_filled, _ = fill_field(widget_dict, "perfrom", pdf_data.get("service_from_formatted", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "perthru.0.0", pdf_data.get("service_to_formatted", ""), fields_filled)
        
        # Patient Name (Locator 8)
        fields_filled, _ = fill_field(widget_dict, "patname", pdf_data.get("pt_name", ""), fields_filled)
        
        # Patient Address (Locator 9)
        fields_filled, _ = fill_field(widget_dict, "pataddress", pdf_data.get("patient_address", ""), fields_filled)
        
        # Birthdate (Locator 10)
        fields_filled, _ = fill_field(widget_dict, "birthdate", pdf_data.get("birthdate_formatted", ""), fields_filled)
        
        # Sex (Locator 11)
        fields_filled, _ = fill_field(widget_dict, "sex", pdf_data.get("sex_code", "1"), fields_filled)
        
        # Admission Date (Locator 12)
        fields_filled, _ = fill_field(widget_dict, "17date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        # Place of Service (Locator 23) - 11=Office
        fields_filled, _ = fill_field(widget_dict, "23place", pdf_data.get("place_of_service", "11"), fields_filled)
        
        # Payer Name (Locator 50)
        fields_filled, _ = fill_field(widget_dict, "50payer.1", pdf_data.get("insurance_name", ""), fields_filled)
        
        # Provider Number (Locator 51)
        fields_filled, _ = fill_field(widget_dict, "51providernum.1", pdf_data.get("insurance_id", ""), fields_filled)
        
        # Accept Assignment (Locator 52)
        fields_filled, _ = fill_field(widget_dict, "52asgben.1", pdf_data.get("accept_assignment_code", "N"), fields_filled)
        
        # Prior Payments (Locator 54)
        fields_filled, _ = fill_field(widget_dict, "54prior.1", pdf_data.get("amt_paid", "0.00"), fields_filled)
        
        # Estimated Amount Due (Locator 55)
        fields_filled, _ = fill_field(widget_dict, "55est.1", pdf_data.get("total_charge", "0.00"), fields_filled)
        
        # NPI (Locator 56)
        fields_filled, _ = fill_field(widget_dict, "56", pdf_data.get("billing_provider_npi", ""), fields_filled)
        
        # Insured's Name (Locator 58)
        fields_filled, _ = fill_field(widget_dict, "58insname.1", pdf_data.get("pt_name", ""), fields_filled)
        
        # Patient Relationship (Locator 59)
        fields_filled, _ = fill_field(widget_dict, "59prel.1", pdf_data.get("rel_code", "18"), fields_filled)
        
        # Insured's ID (Locator 60)
        fields_filled, _ = fill_field(widget_dict, "60cert.1", pdf_data.get("insurance_id", ""), fields_filled)
        
        # Treatment Authorization (Locator 63)
        fields_filled, _ = fill_field(widget_dict, "63treatment.1", pdf_data.get("prior_auth_number", ""), fields_filled)
        
        # Principal Diagnosis (Locator 67)
        fields_filled, _ = fill_field(widget_dict, "67prin", pdf_data.get("diagnosis1", ""), fields_filled)
        
        # Principal Procedure Code (Locator 80)
        fields_filled, _ = fill_field(widget_dict, "80code", pdf_data.get("cpt1", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "80date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        # Other Procedure Code (Locator 81)
        fields_filled, _ = fill_field(widget_dict, "81code", pdf_data.get("cpt2", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "81date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        # Additional Procedure Codes
        if pdf_data.get("cpt3"):
            fields_filled, _ = fill_field(widget_dict, "othercode", pdf_data.get("cpt3", ""), fields_filled)
            fields_filled, _ = fill_field(widget_dict, "otherdate", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        if pdf_data.get("cpt4"):
            fields_filled, _ = fill_field(widget_dict, "other2", pdf_data.get("cpt4", ""), fields_filled)
            fields_filled, _ = fill_field(widget_dict, "other2date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        if pdf_data.get("cpt5"):
            fields_filled, _ = fill_field(widget_dict, "other3", pdf_data.get("cpt5", ""), fields_filled)
            fields_filled, _ = fill_field(widget_dict, "other3date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        if pdf_data.get("cpt6"):
            fields_filled, _ = fill_field(widget_dict, "other4", pdf_data.get("cpt6", ""), fields_filled)
            fields_filled, _ = fill_field(widget_dict, "other4date", pdf_data.get("service_from_formatted", ""), fields_filled)
        
        # Attending Physician NPI and Name
        fields_filled, _ = fill_field(widget_dict, "NPI.0.0", pdf_data.get("billing_provider_npi", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "NPI.0.1", pdf_data.get("physician_signature", ""), fields_filled)
        
        # Remarks (Locator 80)
        remarks = pdf_data.get("diagnosis1_desc", "")
        if len(remarks) > 80:
            remarks = remarks[:77] + "..."
        fields_filled, _ = fill_field(widget_dict, "remarks", remarks, fields_filled)
        
        # Provider Signature
        fields_filled, _ = fill_field(widget_dict, "provrepsign", pdf_data.get("physician_signature", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "signdate", pdf_data.get("physician_date", ""), fields_filled)
        
        # Patient Signature
        fields_filled, _ = fill_field(widget_dict, "patsign", pdf_data.get("patient_signature", ""), fields_filled)
        fields_filled, _ = fill_field(widget_dict, "patsigndate", pdf_data.get("patient_signature_date", ""), fields_filled)
        
        # Fill Revenue Section
        print("\n=== Filling Revenue Codes Section ===")
        cpt_codes = pdf_data["cpt_codes"]
        max_lines = 23
        lines_to_fill = min(len(cpt_codes), max_lines)
        
        for i in range(lines_to_fill):
            cpt = cpt_codes[i]
            line_num = i + 1
            
            # Revenue Code
            fields_filled, _ = fill_field(widget_dict, f"revcd42.{line_num}", cpt.get("rev_code", "300"), fields_filled)
            
            # Description
            desc = cpt["desc"][:28] if len(cpt["desc"]) > 28 else cpt["desc"]
            fields_filled, _ = fill_field(widget_dict, f"43desc.{line_num}", desc, fields_filled)
            
            # HCPCS Code
            fields_filled, _ = fill_field(widget_dict, f"44hcps.{line_num}", cpt["code"], fields_filled)
            
            # Service Date
            fields_filled, _ = fill_field(widget_dict, f"45servdate.{line_num}", pdf_data.get("service_from_formatted", ""), fields_filled)
            
            # Units (default to 1)
            fields_filled, _ = fill_field(widget_dict, f"46servunits.{line_num}", "1", fields_filled)
            
            # Total Charges
            try:
                charge = float(cpt["charge"] or 0)
                charge_str = f"{charge:.2f}"
                fields_filled, _ = fill_field(widget_dict, f"47totalcharges.{line_num}", charge_str, fields_filled)
            except:
                fields_filled, _ = fill_field(widget_dict, f"47totalcharges.{line_num}", "0.00", fields_filled)
            
            print(f"  Line {line_num}: {cpt.get('rev_code', '300')} | {cpt['desc'][:20]}... | ${cpt['charge']}")
        
        # Calculate and fill total
        total_charge = pdf_data.get("total_charge", "0.00")
        print(f"\nTotal Charge: ${total_charge}")
        
        # Try to fill total field
        total_fields = ["total", "TOTAL", "totals", "47total", "TOTALS"]
        for total_field in total_fields:
            fields_filled, filled = fill_field(widget_dict, total_field, total_charge, fields_filled)
            if filled:
                break
        
        # Write filled PDF
        filled_pdf_bytes = pdf.write()
        pdf.close()
        
        # Keep AcroForm widgets intact so browser/PDF viewers preserve the
        # official institutional claim appearance. Do not flatten/delete fields.
        flattened_pdf_bytes = filled_pdf_bytes
        print(f"UB-04 PDF generated without flattening: size={len(flattened_pdf_bytes)} bytes, fields_filled={fields_filled}")
        try:
            with open("/tmp/debug_ub04.pdf", "wb") as debug_file:
                debug_file.write(flattened_pdf_bytes)
        except OSError as debug_error:
            print(f"UB-04 debug PDF write skipped: {debug_error}")
        
        # Generate output filename
        patient_name_safe = pdf_data.get("pt_name", "Unknown").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_key = f"UB04_{patient_name_safe}_{timestamp}_{uuid.uuid4().hex[:8]}.pdf"
        out_key=f"forms/{patient_id}/UB04_{uuid.uuid4()}.pdf"
        
        # Upload to S3
        s3.put_object(
            Bucket=DEST_BUCKET,
            Key=out_key,
            Body=flattened_pdf_bytes,
            ContentType="application/pdf",
            Metadata={
                "patient": patient_name_safe,
                "total-charge": str(total_charge),
                "filled-fields": str(fields_filled),
                "cpt-codes": str(lines_to_fill)
            }
        )
        print(f"UB-04 PDF uploaded: s3://{DEST_BUCKET}/{out_key}")
        
        if sessionid and sessionid != "unknown-session":
            update_job(sessionid, progress="UB04_FORM", status="SUCCESS")
        print(
            f"UB-04 validation: template_fields={len(widget_dict)}, "
            f"fields_filled={fields_filled}, cpt_lines={lines_to_fill}, pdf_size={len(flattened_pdf_bytes)}"
        )
        
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": DEST_BUCKET, "Key": out_key},
            ExpiresIn=3600
        )
        print("UB-04 presigned URL generated")
        
        return {
            "status": "success",
            "message": f"UB-04 generated for {patient_id}",
            "file_key": out_key,
            "file_url": url,
            "fields_filled": fields_filled,
            "cpt_codes_filled": lines_to_fill,
            "total_charge": total_charge,
            "patient_name": pdf_data.get("pt_name", "Unknown"),
            "s3_path": f"s3://{DEST_BUCKET}/{out_key}"
        }
        
    except Exception as e:
        print(f"ERROR generating UB-04 form: {str(e)}")
        traceback.print_exc()
        if sessionid and sessionid != "unknown-session":
            update_job(sessionid, progress="UB04_FORM", status="ERROR")
        return {
            "status": "error",
            "message": f"Failed to generate UB-04 form: {str(e)}"
        }

# ======================================================================
# EDI GENERATION
# ======================================================================
def seg(*elements):
    return "*".join([x if x else "" for x in elements]) + "~"

def build_837I(claim):
    """Build 837I EDI for Institutional claims"""
    edi = []
    now = datetime.utcnow()
    
    # ISA Segment
    edi.append(seg(
        "ISA", "00", "", "00", "",
        "ZZ", "SENDERID", "ZZ", "RECEIVERID",
        now.strftime("%y%m%d"), now.strftime("%H%M"),
        "U", "00401", "000000001", "0", "P", ":"
    ))
    
    # GS Segment
    edi.append(seg(
        "GS", "HC", "SENDERID", "RECEIVERID",
        now.strftime("%Y%m%d"), now.strftime("%H%M"),
        "1", "X", "005010X223A2"
    ))
    
    # ST Segment
    edi.append(seg("ST", "837", "0001"))
    
    # BHT Segment
    edi.append(seg(
        "BHT", "0019", "00", "CLM" + now.strftime("%H%M%S"),
        now.strftime("%Y%m%d"), now.strftime("%H%M")
    ))
    
    # Provider info
    provider_name = claim.get("service_facility_name", "PROVIDER GROUP")
    provider_npi = (
        claim.get("billing_provider_npi")
        or claim.get("provider_npi")
        or (claim.get("provider") or {}).get("npi")
        or ""
    )
    edi.append(seg("NM1", "41", "2", provider_name, "", "", "", "", "46", provider_npi))
    edi.append(seg("PER", "IC", "EDI DEPARTMENT", "TE", "5551234567"))
    
    # Receiver info
    insurance_name = claim.get("insurance_name", "INSURANCE COMPANY")
    edi.append(seg("NM1", "40", "2", insurance_name, "", "", "", "", "46", "RECEIVERID"))
    
    # Billing Provider
    edi.append(seg("HL", "1", "", "20", "1"))
    edi.append(seg("PRV", "BI", "PXC", "261Q00000X"))
    edi.append(seg("NM1", "85", "2", provider_name, "", "", "", "", "XX", provider_npi))
    edi.append(seg("N3", claim.get("service_facility_address", "123 MAIN ST")))
    edi.append(seg("N4", claim.get("service_facility_city", "CITY"), claim.get("service_facility_state", "ST"), claim.get("service_facility_zip", "12345")))
    
    # Patient info
    edi.append(seg("HL", "2", "1", "22", "0"))
    full_name = claim.get("pt_name", "")
    first_name = full_name.split(" ")[0] if full_name else ""
    last_name = " ".join(full_name.split(" ")[1:]) if full_name else ""
    
    rel_code = "18"
    if claim.get("rel_to_ins", "").lower() == "spouse":
        rel_code = "01"
    elif claim.get("rel_to_ins", "").lower() == "child":
        rel_code = "19"
    
    edi.append(seg("SBR", "P", rel_code, "", "", "", "", "", "", "Y"))
    edi.append(seg("NM1", "IL", "1", last_name, first_name, "", "", "MI", claim.get("insurance_id", "")))
    edi.append(seg("N3", claim.get("pt_street", "")))
    edi.append(seg("N4", claim.get("pt_city", ""), claim.get("pt_state", ""), claim.get("pt_zip", "")))
    
    # Demographic
    birth_date = f"{claim.get('birth_yy', '')}{claim.get('birth_mm', '')}{claim.get('birth_dd', '')}"
    sex = "F" if claim.get("sex", "").upper() == "F" else "M"
    edi.append(seg("DMG", "D8", birth_date, sex))
    
    # Claim info
    edi.append(seg("HL", "3", "2", "23", "0"))
    edi.append(seg("CLM", 
                   claim.get("patient_id", "UNKNOWN"),
                   claim.get("total_charge", "0.00"),
                   "",
                   "11:A:1:Y",
                   "",
                   "Y",
                   "Y",
                   "",
                   ""))
    
    # Dates
    statement_from = f"{claim.get('service_from_yy', '')}{claim.get('service_from_mm', '')}{claim.get('service_from_dd', '')}"
    statement_to = f"{claim.get('service_to_yy', '')}{claim.get('service_to_mm', '')}{claim.get('service_to_dd', '')}"
    
    if statement_from == statement_to:
        edi.append(seg("DTP", "434", "D8", statement_from))
    else:
        edi.append(seg("DTP", "434", "RD8", f"{statement_from}-{statement_to}"))
    
    edi.append(seg("DTP", "435", "D8", statement_from))
    
    if statement_from != statement_to:
        edi.append(seg("DTP", "096", "D8", statement_to))
    
    edi.append(seg("CL1", "1", "", ""))
    
    # Diagnosis
    diagnosis_code = claim.get("diagnosis1", "")
    if diagnosis_code:
        edi.append(seg("HI", f"BK:{diagnosis_code}"))
    
    # Service lines
    cpt_count = 0
    for i in range(1, 15):
        cpt_key = f"cpt{i}"
        charge_key = f"cpt{i}_charge"
        
        if cpt_key in claim and claim[cpt_key]:
            cpt_count += 1
            edi.append(seg("HL", f"{3 + cpt_count}", "3", "24", "0"))
            edi.append(seg("LIN", "", "", "", f"N4{claim[cpt_key]}"))
            
            charge_amount = claim.get(charge_key, "0.00")
            edi.append(seg("SV1", "HC:" + claim[cpt_key], charge_amount, "UN", "1", "", "", "", "N"))
            edi.append(seg("DTP", "472", "D8", statement_from))
    
    # Segments count
    total_segments = len(edi) + 2
    edi.append(seg("SE", str(total_segments), "0001"))
    edi.append(seg("GE", "1", "1"))
    edi.append(seg("IEA", "1", "000000001"))
    
    return "\n".join(edi)

def generate_ub04_edi(claim_data, patient_id, sessionid):
    """Generate UB-04 EDI (837I)"""
    if not EDI_OUTPUT_BUCKET:
        print("nO BUCKET")
        return {
            "status": "skipped",
            "message": "EDI_OUTPUT_BUCKET not configured"
        }
    
    try:
        edi_text = build_837I(claim_data)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        patient_name_safe = claim_data.get("pt_name", "Unknown").replace(" ", "_")
        edi_key = f"edi/{patient_id}/{patient_id}_{timestamp}_837I.edi"
        print("STRATED EDI ")
        s3.put_object(
            Bucket=EDI_OUTPUT_BUCKET,
            Key=edi_key,
            Body=edi_text.encode("utf-8"),
            ContentType="text/plain"
        )
        
        if sessionid and sessionid != "unknown-session":
            update_job(sessionid, progress="UB04_EDI", status="SUCCESS")
        
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": EDI_OUTPUT_BUCKET, "Key": edi_key},
            ExpiresIn=3600
        )
        
        return {
            "status": "success",
            "patient_id": patient_id,
            "edi_key": edi_key,
            "download_url": presigned_url,
            "edi_type": "837I",
            "form_type": "UB-04"
        }
        
    except Exception as e:
        print(f"ERROR generating UB-04 EDI: {str(e)}")
        if sessionid and sessionid != "unknown-session":
            update_job(sessionid, progress="UB04_EDI", status="ERROR")
        return {
            "status": "error",
            "message": f"Failed to generate UB-04 EDI: {str(e)}"
        }

# ======================================================================
# MAIN HANDLER
# ======================================================================
def lambda_handler(event, context):
    print("Lambda invoked", event)

    # ✅ REQUIRED INPUT
    patient_id = event.get("patientId") or event.get("patient_id")
    sessionid = event.get("sessionId", "unknown-session")
    claim_data = event.get("data")
    mode = event.get("mode", "both")

    if not patient_id or not claim_data:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "error",
                "message": "patientId and data are required"
            })
        }

    results = {}

    try:
        if mode in ("form", "both"):
            print("PDF FILLING==>")
            results["form"] = generate_ub04_form(
                claim_data=claim_data,
                patient_id=patient_id,
                sessionid=sessionid
            )
            time.sleep(0.5)

        if mode in ("edi", "both"):
            print("Generating EDI ==>")
            results["edi"] = generate_ub04_edi(
                claim_data=claim_data,
                patient_id=patient_id,
                sessionid=sessionid
            )
        print("RESULTS :" ,results )
        return {
            "statusCode": 200,
            "body": json.dumps(results)
        }

    except Exception as e:
        traceback.print_exc()

        if sessionid and sessionid != "unknown-session":
            update_job(sessionid, progress="UB04", status="ERROR")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e)
            })
        }

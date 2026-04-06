import boto3
from datetime import datetime
from decimal import Decimal

# -------------------------
# 🔹 DynamoDB Setup
# -------------------------
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("ehr-claims-table")


# -------------------------
# 🔥 FLOAT → DECIMAL (FOR SAVE)
# -------------------------
def convert_floats_to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(i) for i in obj]
    return obj


# -------------------------
# 🔥 DECIMAL → FLOAT (FOR RESPONSE)
# -------------------------
def convert_decimal(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    return obj


# -------------------------
# 🔹 SAVE RECORD
# -------------------------
def save_record(result):
    try:
        claim_id = result.get("claim_id")

        item = {
            "claim_id": claim_id,
            "file": result.get("file"),
            "status": result.get("status"),
            "template": result.get("template"),
            "template_scores": result.get("template_scores"),

            # 🔥 CORE DATA
            "claim": result.get("claim"),
            "pipeline": result.get("pipeline", {}),

            # 🔥 ORCHESTRATION
            "case": result.get("case"),

            # 🔥 OUTPUTS
            "denial": result.get("denial"),
            "payment": result.get("payment"),

            "created_at": datetime.utcnow().isoformat()
        }

        # ✅ Convert for DynamoDB
        item = convert_floats_to_decimal(item)

        print("🧠 FINAL ITEM TO SAVE:", item)

        table.put_item(Item=item)

        print("✅ Saved:", claim_id)

    except Exception as e:
        print("❌ DB Error:", str(e))


# -------------------------
# 🔹 GET ALL RECORDS
# -------------------------
def get_all_records():
    try:
        response = table.scan()
        items = response.get("Items", [])

        # ✅ Filter only valid records
        items = [i for i in items if "claim_id" in i]

        # 🔥 Convert Decimal → float
        return [convert_decimal(i) for i in items]

    except Exception as e:
        print("❌ Fetch Error:", str(e))
        return []


# -------------------------
# 🔹 GET RECORD BY ID
# -------------------------
def get_record_by_id(record_id):
    try:
        response = table.get_item(Key={"claim_id": record_id})
        item = response.get("Item")

        return convert_decimal(item) if item else None

    except Exception as e:
        print("❌ Fetch by ID Error:", str(e))
        return None


# -------------------------
# 🔹 UPDATE CLAIM
# -------------------------
def update_claim_data(claim_id, updated_claim):
    table.update_item(
        Key={"claim_id": claim_id},
        UpdateExpression="SET #c = :c",
        ExpressionAttributeNames={"#c": "claim"},
        ExpressionAttributeValues={
            ":c": convert_floats_to_decimal(updated_claim)
        }
    )


# -------------------------
# 🔹 UPDATE STATUS
# -------------------------
def update_record_status(claim_id, status):
    try:
        table.update_item(
            Key={"claim_id": claim_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status}
        )

        print(f"✅ Status updated: {claim_id} → {status}")

    except Exception as e:
        print("❌ Update Status Error:", str(e))


# -------------------------
# 🔹 UPDATE CASE
# -------------------------
def update_case(claim_id, case_data):
    table.update_item(
        Key={"claim_id": claim_id},
        UpdateExpression="SET #c = :c",
        ExpressionAttributeNames={"#c": "case"},
        ExpressionAttributeValues={
            ":c": convert_floats_to_decimal(case_data)
        }
    )
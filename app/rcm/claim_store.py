from sqlalchemy import text
from datetime import datetime
from app.db.database import engine
from psycopg2.extras import Json
import uuid
import time


BATCH_SIZE = 100

_RECENT_SAVE_CACHE = {}
_SAVE_DEDUPE_SECONDS = 5


def should_skip_duplicate_save(claim_id, status, stage):
    claim_id = str(claim_id or "").strip()
    status = str(status or "").strip()
    stage = str(stage or "").strip()

    if not claim_id:
        return False

    key = f"{claim_id}:{status}:{stage}"
    now = time.time()

    last_saved = _RECENT_SAVE_CACHE.get(key)

    if last_saved and now - last_saved < _SAVE_DEDUPE_SECONDS:
        print(f"⚠️ [ClaimStore] Skipping duplicate save for {key}")
        return True

    _RECENT_SAVE_CACHE[key] = now
    return False


def save_claim(claim_id, status, stage, payload, total_charge=0):
    claim_id = str(claim_id or "").strip()

    if not claim_id:
        raise ValueError("save_claim requires claim_id")

    status = status or "UNKNOWN"
    stage = stage or "UNKNOWN"

    if should_skip_duplicate_save(claim_id, status, stage):
        return None

    query = text("""
        INSERT INTO claims (
            claim_id, status, stage, total_charge, payload, created_at, updated_at
        ) VALUES (
            :claim_id, :status, :stage, :total_charge, :payload, :created_at, :updated_at
        )
        ON CONFLICT (claim_id) DO UPDATE SET
            status = EXCLUDED.status,
            stage = EXCLUDED.stage,
            total_charge = EXCLUDED.total_charge,
            payload = EXCLUDED.payload,
            updated_at = EXCLUDED.updated_at
    """)

    now = datetime.utcnow()

    with engine.begin() as conn:
        conn.execute(query, {
            "claim_id": claim_id,
            "status": status,
            "stage": stage,
            "total_charge": total_charge or 0,
            "payload": Json(payload or {}),
            "created_at": now,
            "updated_at": now,
        })

    print(f"✅ [ClaimStore] Claim saved: {claim_id} | {status} | {stage}")
    return {
        "claim_id": claim_id,
        "status": status,
        "stage": stage,
        "saved": True,
    }


def update_claim(claim_id, status, stage=None):
    claim_id = str(claim_id or "").strip()

    if not claim_id:
        raise ValueError("update_claim requires claim_id")

    if stage:
        query = text("""
            UPDATE claims
            SET status = :status,
                stage = :stage,
                updated_at = :updated_at
            WHERE claim_id = :claim_id
        """)
        params = {
            "claim_id": claim_id,
            "status": status,
            "stage": stage,
            "updated_at": datetime.utcnow(),
        }
    else:
        query = text("""
            UPDATE claims
            SET status = :status,
                updated_at = :updated_at
            WHERE claim_id = :claim_id
        """)
        params = {
            "claim_id": claim_id,
            "status": status,
            "updated_at": datetime.utcnow(),
        }

    with engine.begin() as conn:
        result = conn.execute(query, params)

    print(f"🔄 [ClaimStore] Claim updated: {claim_id} → {status}")

    return {
        "claim_id": claim_id,
        "status": status,
        "stage": stage,
        "updated": True,
        "rowcount": result.rowcount,
    }


def get_claim(claim_id):
    claim_id = str(claim_id or "").strip()

    if not claim_id:
        return None

    query = text("""
        SELECT claim_id, status, stage, total_charge, payload, created_at, updated_at
        FROM claims
        WHERE claim_id = :claim_id
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"claim_id": claim_id}).mappings().first()

    return dict(result) if result else None


def bulk_insert_claims(claims_list):
    claims_list = claims_list or []

    print(f"🔥 [ClaimStore] BULK INSERT CALLED: {len(claims_list)}")

    if not claims_list:
        return {
            "inserted": 0,
            "failed": 0,
        }

    query = text("""
        INSERT INTO claims (
            claim_id, status, stage, total_charge, payload, created_at, updated_at
        )
        VALUES (
            :id, :status, :stage, :charge, :payload, :created, :updated
        )
        ON CONFLICT (claim_id) DO NOTHING
    """)

    inserted = 0
    failed = 0

    with engine.begin() as conn:
        for i in range(0, len(claims_list), BATCH_SIZE):
            batch = claims_list[i:i + BATCH_SIZE]
            now = datetime.utcnow()

            try:
                rows = []

                for claim in batch:
                    claim_id = claim.get("claim_id")

                    if not claim_id:
                        failed += 1
                        print("⚠️ [ClaimStore] Skipping bulk claim without claim_id")
                        continue

                    rows.append({
                        "id": claim_id,
                        "status": claim.get("status", "EXTRACTED"),
                        "stage": claim.get("stage", "FINAL"),
                        "charge": claim.get("total_charge", 0),
                        "payload": Json(claim.get("payload") or claim),
                        "created": now,
                        "updated": now,
                    })

                if not rows:
                    continue

                conn.execute(query, rows)

                inserted += len(rows)

                print(f"✅ [ClaimStore] Inserted batch {i} → {i + len(rows)}")

            except Exception as error:
                failed += len(batch)
                print("❌ [ClaimStore] INSERT ERROR:", str(error))

    return {
        "inserted": inserted,
        "failed": failed,
    }


def create_case(claim_id, error, case_type=None, metadata=None):
    claim_id = str(claim_id or "").strip()

    if not claim_id:
        raise ValueError("create_case requires claim_id")

    if case_type:
        error = f"[{case_type}] {error}"

    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE cases
            ADD COLUMN IF NOT EXISTS error_message TEXT
        """))

        columns = {
            row[0]
            for row in conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'cases'
            """))
        }

        now = datetime.utcnow()

        values = {
            "case_id": f"CASE-{uuid.uuid4().hex[:10]}",
            "claim_id": claim_id,
            "title": "Dead Letter Queue Review" if case_type == "DLQ" else "Claim Review",
            "description": error,
            "error_message": error,
            "case_type": case_type or "HITL",
            "status": "OPEN",
            "priority": "HIGH" if case_type == "DLQ" else "MEDIUM",
            "assigned_role": "QA_TEAM",
            "metadata_json": Json(metadata or {}),
            "created_by": "SYSTEM",
            "created_at": now,
            "updated_at": now,
        }

        insert_columns = [
            column
            for column in values
            if column in columns
        ]

        placeholders = [
            f":{column}"
            for column in insert_columns
        ]

        conn.execute(
            text(f"""
                INSERT INTO cases ({", ".join(insert_columns)})
                VALUES ({", ".join(placeholders)})
            """),
            {
                column: values[column]
                for column in insert_columns
            },
        )

    print(f"🧾 [ClaimStore] Case created: {claim_id}")

    return claim_id
# from __future__ import annotations

# from datetime import datetime
# from typing import Any, Dict

# from sqlalchemy import text
# from psycopg2.extras import Json

# from app.db.database import engine


# def persist_extraction_metadata(claim_id: str, claim: Dict[str, Any], textract_or_parsed: Dict[str, Any] | None = None) -> None:
#     if not claim_id:
#         return

#     field_rows = [
#         {
#             "claim_id": claim_id,
#             "field": item.get("field"),
#             "value": item.get("value"),
#             "confidence": float(item.get("confidence") or 0),
#             "source": "universal_extraction",
#             "form_type": item.get("form_type") or claim.get("form_type"),
#             "created_at": datetime.utcnow(),
#         }
#         for item in claim.get("field_confidence", [])
#         if item.get("field")
#     ]

#     entity_rows = []
#     for block in (textract_or_parsed or {}).get("Blocks", [])[:600]:
#         if block.get("BlockType") not in {"LINE", "WORD", "SELECTION_ELEMENT"}:
#             continue
#         entity_rows.append({
#             "claim_id": claim_id,
#             "entity_type": block.get("BlockType"),
#             "text": block.get("Text") or block.get("SelectionStatus", ""),
#             "confidence": float(block.get("Confidence") or 0),
#             "page": int(block.get("Page") or 1),
#             "raw": Json(block),
#             "created_at": datetime.utcnow(),
#         })

#     with engine.begin() as conn:
#         conn.execute(text("ALTER TABLE extraction_confidence ADD COLUMN IF NOT EXISTS value TEXT"))
#         conn.execute(text("ALTER TABLE extraction_confidence ADD COLUMN IF NOT EXISTS form_type VARCHAR"))
#         if field_rows:
#             conn.execute(text("""
#                 INSERT INTO extraction_confidence
#                 (claim_id, field, value, confidence, source, form_type, created_at)
#                 VALUES
#                 (:claim_id, :field, :value, :confidence, :source, :form_type, :created_at)
#             """), field_rows)

#         if entity_rows:
#             conn.execute(text("""
#                 INSERT INTO textract_entities
#                 (claim_id, entity_type, text, confidence, page, raw, created_at)
#                 VALUES
#                 (:claim_id, :entity_type, :text, :confidence, :page, :raw, :created_at)
#             """), entity_rows)


from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text

from app.db.database import engine


MAX_TEXTRACT_BLOCKS_TO_STORE = 1200


def persist_extraction_metadata(
    claim_id: str,
    claim: Dict[str, Any],
    textract_or_parsed: Dict[str, Any] | None = None,
) -> None:
    """
    Persist extraction debug metadata for a claim.

    Stores:
    - field-level confidence from claim["field_confidence"]
    - Textract LINE / WORD / SELECTION_ELEMENT entities
    - extraction summary metadata
    - source file reference

    This helps debug original uploaded file extraction later.
    """

    start_time = time.time()

    if not claim_id:
        print("⚠️ [ExtractionStore] Skipped: missing claim_id")
        return

    claim = claim or {}
    textract_or_parsed = textract_or_parsed or {}

    print("\n" + "-" * 80)
    print("🗄️ [ExtractionStore] STARTED")
    print(f"🧾 Claim ID: {claim_id}")
    print(f"📄 Form type: {claim.get('form_type')}")
    print("-" * 80)

    try:
        # ---------------------------------------------------
        # Step 1: Ensure schema columns exist
        # ---------------------------------------------------
        print("➡️ [1] Ensuring extraction tables have required columns...")

        with engine.begin() as conn:
            _ensure_schema(conn)

        # ---------------------------------------------------
        # Step 2: Build rows
        # ---------------------------------------------------
        print("➡️ [2] Building extraction rows...")

        field_rows = _build_field_rows(claim_id, claim)
        entity_rows = _build_entity_rows(claim_id, textract_or_parsed)
        summary_row = _build_summary_row(claim_id, claim, textract_or_parsed)

        print(f"📋 Field confidence rows: {len(field_rows)}")
        print(f"🔎 Textract entity rows: {len(entity_rows)}")

        # ---------------------------------------------------
        # Step 3: Insert rows
        # ---------------------------------------------------
        print("➡️ [3] Persisting extraction metadata...")

        with engine.begin() as conn:
            if field_rows:
                conn.execute(text("""
                    INSERT INTO extraction_confidence
                    (
                        claim_id,
                        field,
                        value,
                        confidence,
                        source,
                        form_type,
                        created_at
                    )
                    VALUES
                    (
                        :claim_id,
                        :field,
                        :value,
                        :confidence,
                        :source,
                        :form_type,
                        :created_at
                    )
                """), field_rows)

            if entity_rows:
                conn.execute(text("""
                    INSERT INTO textract_entities
                    (
                        claim_id,
                        entity_type,
                        text,
                        confidence,
                        page,
                        raw,
                        created_at
                    )
                    VALUES
                    (
                        :claim_id,
                        :entity_type,
                        :text,
                        :confidence,
                        :page,
                        CAST(:raw AS JSONB),
                        :created_at
                    )
                """), entity_rows)

            # Optional summary table.
            # If table does not exist, this safely no-ops after schema creation.
            conn.execute(text("""
                INSERT INTO extraction_metadata
                (
                    claim_id,
                    source_file,
                    processor,
                    form_type,
                    document_type,
                    extraction_confidence,
                    confidence_status,
                    requires_human_review,
                    missing_fields,
                    service_count,
                    raw_fields_count,
                    raw_tables_count,
                    raw_text_length,
                    textract_metadata,
                    created_at
                )
                VALUES
                (
                    :claim_id,
                    CAST(:source_file AS JSONB),
                    :processor,
                    :form_type,
                    :document_type,
                    :extraction_confidence,
                    :confidence_status,
                    :requires_human_review,
                    CAST(:missing_fields AS JSONB),
                    :service_count,
                    :raw_fields_count,
                    :raw_tables_count,
                    :raw_text_length,
                    CAST(:textract_metadata AS JSONB),
                    :created_at
                )
            """), summary_row)

        duration_seconds = round(time.time() - start_time, 2)

        print("✅ [ExtractionStore] COMPLETED")
        print(f"⏱️ Duration: {duration_seconds}s")
        print("-" * 80 + "\n")

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [ExtractionStore] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("-" * 80 + "\n")

        raise


def _ensure_schema(conn) -> None:
    """
    Adds missing columns/tables needed for extraction metadata.

    In production, move this into Alembic migrations.
    Keeping it here is okay for development.
    """

    conn.execute(text("""
        ALTER TABLE extraction_confidence
        ADD COLUMN IF NOT EXISTS value TEXT
    """))

    conn.execute(text("""
        ALTER TABLE extraction_confidence
        ADD COLUMN IF NOT EXISTS form_type VARCHAR
    """))

    conn.execute(text("""
        ALTER TABLE textract_entities
        ADD COLUMN IF NOT EXISTS raw JSONB
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS extraction_metadata (
            id SERIAL PRIMARY KEY,
            claim_id VARCHAR NOT NULL,
            source_file JSONB,
            processor VARCHAR,
            form_type VARCHAR,
            document_type VARCHAR,
            extraction_confidence FLOAT,
            confidence_status VARCHAR,
            requires_human_review BOOLEAN,
            missing_fields JSONB,
            service_count INTEGER,
            raw_fields_count INTEGER,
            raw_tables_count INTEGER,
            raw_text_length INTEGER,
            textract_metadata JSONB,
            created_at TIMESTAMP
        )
    """))


def _build_field_rows(
    claim_id: str,
    claim: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []

    for item in claim.get("field_confidence", []) or []:
        field = item.get("field")

        if not field:
            continue

        rows.append({
            "claim_id": claim_id,
            "field": field,
            "value": item.get("value"),
            "confidence": safe_float(item.get("confidence")),
            "source": item.get("source") or "universal_extraction",
            "form_type": item.get("form_type") or claim.get("form_type"),
            "created_at": datetime.utcnow(),
        })

    return rows


def _build_entity_rows(
    claim_id: str,
    textract_or_parsed: Dict[str, Any],
) -> List[Dict[str, Any]]:
    blocks = textract_or_parsed.get("Blocks", []) or []

    rows = []

    for block in blocks[:MAX_TEXTRACT_BLOCKS_TO_STORE]:
        if block.get("BlockType") not in {"LINE", "WORD", "SELECTION_ELEMENT"}:
            continue

        rows.append({
            "claim_id": claim_id,
            "entity_type": block.get("BlockType"),
            "text": block.get("Text") or block.get("SelectionStatus", ""),
            "confidence": safe_float(block.get("Confidence")),
            "page": safe_int(block.get("Page"), default=1),
            "raw": json.dumps(block, default=str),
            "created_at": datetime.utcnow(),
        })

    return rows


def _build_summary_row(
    claim_id: str,
    claim: Dict[str, Any],
    textract_or_parsed: Dict[str, Any],
) -> Dict[str, Any]:
    extraction = claim.get("extraction") or {}
    intake = claim.get("intake") or {}
    source_file = claim.get("source_file") or {}
    metadata = textract_or_parsed.get("metadata") or {}

    textract_metadata = (
        metadata.get("textract_metadata")
        or extraction.get("textract_metadata")
        or {}
    )

    return {
        "claim_id": claim_id,
        "source_file": json.dumps(source_file, default=str),
        "processor": (
            intake.get("processor")
            or extraction.get("processor")
            or "unknown"
        ),
        "form_type": claim.get("form_type"),
        "document_type": claim.get("document_type"),
        "extraction_confidence": safe_float(
            claim.get("extraction_confidence")
            or extraction.get("extraction_confidence")
        ),
        "confidence_status": claim.get("confidence_status"),
        "requires_human_review": bool(claim.get("requires_human_review")),
        "missing_fields": json.dumps(claim.get("missing_fields") or [], default=str),
        "service_count": len(claim.get("services") or []),
        "raw_fields_count": safe_int(
            extraction.get("raw_fields_count")
            or metadata.get("field_count"),
            default=0,
        ),
        "raw_tables_count": safe_int(
            extraction.get("raw_tables_count")
            or metadata.get("table_count"),
            default=0,
        ),
        "raw_text_length": safe_int(
            extraction.get("raw_text_length")
            or len(str(textract_or_parsed.get("text") or "")),
            default=0,
        ),
        "textract_metadata": json.dumps(textract_metadata, default=str),
        "created_at": datetime.utcnow(),
    }


def safe_float(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return default
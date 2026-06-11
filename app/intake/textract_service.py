import os
import time

import boto3
from botocore.exceptions import ClientError

from app.utils.terminal_logger import (
    EMOJI_EXTRACTION,
    EMOJI_FILE,
    EMOJI_SUCCESS,
    log_exception,
    log_terminal,
)


textract = boto3.client("textract", region_name="us-east-1")

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
}

PDF_EXTENSIONS = {
    ".pdf",
}

DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_MAX_POLL_ATTEMPTS = 90


def analyze_document(
    bucket,
    key,
    file_extension=None,
    max_poll_attempts=DEFAULT_MAX_POLL_ATTEMPTS,
    poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
):
    start_time = time.time()

    log_terminal(f"OCR/Textract started: s3://{bucket}/{key}", EMOJI_EXTRACTION)
    log_terminal(f"Textract input: bucket={bucket}, key={key}", EMOJI_FILE)

    print("\n" + "=" * 80)
    print("🔎 [TextractService] STARTED")
    print(f"🪣 Bucket: {bucket}")
    print(f"🔑 Key: {key}")

    extension = (file_extension or os.path.splitext(key)[1]).lower()

    print(f"📎 Extension: {extension}")
    print("=" * 80)

    try:
        if extension in IMAGE_EXTENSIONS:
            response = analyze_image_document(
                bucket=bucket,
                key=key,
                extension=extension,
                start_time=start_time,
            )

        elif extension in PDF_EXTENSIONS:
            response = analyze_pdf_document(
                bucket=bucket,
                key=key,
                extension=extension,
                start_time=start_time,
                max_poll_attempts=max_poll_attempts,
                poll_interval_seconds=poll_interval_seconds,
            )

        else:
            raise ValueError(f"Unsupported file extension: {extension}")

    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")

        if error_code == "AccessDeniedException":
            log_exception(f"Textract analyze_document: s3://{bucket}/{key}", error)

            raise PermissionError(
                "Textract access denied. Add Textract AnalyzeDocument/StartDocumentAnalysis "
                "permissions for the IAM user/role used by this app."
            ) from error

        log_exception(f"Textract analyze_document: s3://{bucket}/{key}", error)
        raise

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [TextractService] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("=" * 80 + "\n")

        log_exception(f"Textract analyze_document: s3://{bucket}/{key}", error)
        raise

    log_terminal(f"OCR/Textract completed: s3://{bucket}/{key}", EMOJI_SUCCESS)

    return response


def analyze_image_document(bucket, key, extension, start_time):
    print("➡️ [1] Running synchronous Textract analyze_document for image...")

    response = textract.analyze_document(
        Document={
            "S3Object": {
                "Bucket": bucket,
                "Name": key,
            }
        },
        FeatureTypes=[
            "FORMS",
            "TABLES",
        ],
    )

    duration_seconds = round(time.time() - start_time, 2)

    response["textract_metadata"] = {
        "mode": "sync",
        "status": "SUCCEEDED",
        "bucket": bucket,
        "key": key,
        "extension": extension,
        "duration_seconds": duration_seconds,
        "block_count": len(response.get("Blocks", [])),
        "average_confidence": average_block_confidence(response.get("Blocks", [])),
        "warnings": response.get("Warnings", []),
        "status_message": response.get("StatusMessage"),
    }

    print("✅ Textract image analysis completed")
    print(f"📦 Blocks: {response['textract_metadata']['block_count']}")
    print(f"📊 Avg confidence: {response['textract_metadata']['average_confidence']}")
    print(f"⚠️ Warnings: {response['textract_metadata']['warnings']}")
    print(f"⏱️ Duration: {duration_seconds}s")
    print("=" * 80 + "\n")

    return response


def analyze_pdf_document(
    bucket,
    key,
    extension,
    start_time,
    max_poll_attempts,
    poll_interval_seconds,
):
    print("➡️ [1] Starting asynchronous Textract document analysis for PDF...")

    job = textract.start_document_analysis(
        DocumentLocation={
            "S3Object": {
                "Bucket": bucket,
                "Name": key,
            }
        },
        FeatureTypes=[
            "FORMS",
            "TABLES",
        ],
    )

    job_id = job["JobId"]
    pages = []
    final_status = None
    final_result = {}

    print(f"✅ Textract job started: {job_id}")

    for attempt in range(1, max_poll_attempts + 1):
        result = textract.get_document_analysis(JobId=job_id)
        status = result.get("JobStatus")
        final_status = status
        final_result = result

        print(f"⏳ Textract polling attempt {attempt}/{max_poll_attempts}: {status}")

        if status in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
            pages.extend(result.get("Blocks", []))

            next_token = result.get("NextToken")

            while next_token:
                next_page = textract.get_document_analysis(
                    JobId=job_id,
                    NextToken=next_token,
                )

                pages.extend(next_page.get("Blocks", []))
                next_token = next_page.get("NextToken")

            duration_seconds = round(time.time() - start_time, 2)

            response = {
                "Blocks": pages,
                "textract_metadata": {
                    "mode": "async",
                    "status": status,
                    "job_id": job_id,
                    "bucket": bucket,
                    "key": key,
                    "extension": extension,
                    "duration_seconds": duration_seconds,
                    "block_count": len(pages),
                    "page_count": count_pages(pages),
                    "average_confidence": average_block_confidence(pages),
                    "warnings": result.get("Warnings", []),
                    "status_message": result.get("StatusMessage"),
                },
            }

            if status == "PARTIAL_SUCCESS":
                print("⚠️ Textract PDF analysis partially succeeded")
            else:
                print("✅ Textract PDF analysis completed")

            print(f"📦 Blocks: {len(pages)}")
            print(f"📄 Pages: {response['textract_metadata']['page_count']}")
            print(f"📊 Avg confidence: {response['textract_metadata']['average_confidence']}")
            print(f"⚠️ Warnings: {response['textract_metadata']['warnings']}")
            print(f"⏱️ Duration: {duration_seconds}s")
            print("=" * 80 + "\n")

            return response

        if status == "FAILED":
            raise RuntimeError(
                f"Textract analysis failed for {key}: "
                f"{result.get('StatusMessage') or 'No status message'}"
            )

        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"Textract timed out for {key}. "
        f"Last status={final_status}, "
        f"message={final_result.get('StatusMessage')}, "
        f"attempts={max_poll_attempts}"
    )


class TextractService:
    async def extract(self, bucket, key=None, file_extension=None):
        if key is None and isinstance(bucket, str) and bucket.startswith("s3://"):
            path = bucket[5:]
            bucket, key = path.split("/", 1)

        if not bucket or not key:
            raise ValueError("TextractService.extract requires bucket and key")

        return analyze_document(bucket, key, file_extension)


def extract_textract_data(file_path: str):
    """
    Local-file Textract helper for image files.

    AWS Textract synchronous Bytes input supports image files.
    For PDFs, upload to S3 and use asynchronous Textract.
    """

    start_time = time.time()

    log_terminal(f"OCR/Textract started for local file: {file_path}", EMOJI_EXTRACTION)

    extension = os.path.splitext(file_path)[1].lower()

    if extension not in IMAGE_EXTENSIONS:
        raise ValueError(
            "Local Textract Bytes mode supports image files only. "
            "Upload PDFs to S3 and use async Textract."
        )

    with open(file_path, "rb") as file_obj:
        bytes_data = file_obj.read()

    try:
        response = textract.analyze_document(
            Document={"Bytes": bytes_data},
            FeatureTypes=[
                "FORMS",
                "TABLES",
            ],
        )

        duration_seconds = round(time.time() - start_time, 2)

        response["textract_metadata"] = {
            "mode": "local_bytes",
            "status": "SUCCEEDED",
            "file_path": file_path,
            "extension": extension,
            "duration_seconds": duration_seconds,
            "block_count": len(response.get("Blocks", [])),
            "page_count": count_pages(response.get("Blocks", [])),
            "average_confidence": average_block_confidence(response.get("Blocks", [])),
            "warnings": response.get("Warnings", []),
            "status_message": response.get("StatusMessage"),
        }

        parsed = parse_textract_response(response)

        log_terminal(f"OCR/Textract completed for local file: {file_path}", EMOJI_SUCCESS)

        return parsed

    except Exception as error:
        log_exception(f"Textract local file extraction: {file_path}", error)
        raise


def parse_textract_response(response):
    start_time = time.time()

    log_terminal("Extraction parsing started", EMOJI_EXTRACTION)

    response = response or {}
    blocks = response.get("Blocks", []) or []

    block_map = {
        block["Id"]: block
        for block in blocks
        if block.get("Id")
    }

    key_values = {}
    tables = []
    lines = []
    page_numbers = set()
    confidence_values = []

    for block in blocks:
        block_type = block.get("BlockType")

        if block.get("Page"):
            page_numbers.add(block.get("Page"))

        if block.get("Confidence") is not None:
            confidence_values.append(float(block.get("Confidence")))

        if block_type == "LINE":
            lines.append(block.get("Text", ""))

        if (
            block_type == "KEY_VALUE_SET"
            and "KEY" in block.get("EntityTypes", [])
        ):
            key = get_text(block, block_map)
            value = get_value(block, block_map)

            if key:
                add_key_value(key_values, key, value)

    for block in blocks:
        if block.get("BlockType") == "TABLE":
            tables.append(extract_table(block, block_map))

    duration_seconds = round(time.time() - start_time, 2)

    avg_confidence = (
        round(sum(confidence_values) / len(confidence_values), 2)
        if confidence_values
        else 0
    )

    page_block_count = count_pages(blocks)

    parsed = {
        "fields": key_values,
        "tables": tables,
        "lines": lines,
        "text": "\n".join(lines),
        "metadata": {
            "line_count": len(lines),
            "field_count": len(key_values),
            "table_count": len(tables),
            "page_count": page_block_count or len(page_numbers) or None,
            "block_count": len(blocks),
            "average_confidence": avg_confidence,
            "duration_seconds": duration_seconds,
            "textract_metadata": response.get("textract_metadata", {}),
        },
    }

    log_terminal(
        f"Extraction completed: fields={len(key_values)}, tables={len(tables)}, lines={len(lines)}",
        EMOJI_SUCCESS,
    )

    print("✅ [TextractParser] COMPLETED")
    print(f"📄 Lines: {len(lines)}")
    print(f"📋 Fields: {len(key_values)}")
    print(f"📊 Tables: {len(tables)}")
    print(f"📦 Blocks: {len(blocks)}")
    print(f"📄 Pages: {parsed['metadata']['page_count']}")
    print(f"📈 Avg confidence: {avg_confidence}")
    print(f"⏱️ Parse duration: {duration_seconds}s")

    return parsed


def add_key_value(key_values, key, value):
    clean_key = str(key).strip()

    if not clean_key:
        return

    if clean_key not in key_values:
        key_values[clean_key] = value
        return

    suffix = 2

    while f"{clean_key}_{suffix}" in key_values:
        suffix += 1

    key_values[f"{clean_key}_{suffix}"] = value


def extract_table(table_block, block_map):
    cells = {}
    max_column = 0

    for relationship in table_block.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue

        for child_id in relationship.get("Ids", []):
            cell = block_map.get(child_id)

            if not cell or cell.get("BlockType") != "CELL":
                continue

            row_index = int(cell.get("RowIndex") or 0)
            column_index = int(cell.get("ColumnIndex") or 0)

            if row_index <= 0 or column_index <= 0:
                continue

            cells[(row_index, column_index)] = get_text(cell, block_map)
            max_column = max(max_column, column_index)

    rows = []
    row_indexes = sorted({row for row, _ in cells})

    for row_index in row_indexes:
        rows.append([
            cells.get((row_index, column_index), "")
            for column_index in range(1, max_column + 1)
        ])

    return {
        "id": table_block.get("Id"),
        "rows": rows,
        "row_count": len(rows),
        "column_count": max_column,
        "raw": table_block,
    }


def get_text(block, block_map):
    text_parts = []

    for relationship in block.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue

        for child_id in relationship.get("Ids", []):
            word = block_map.get(child_id)

            if not word:
                continue

            if word.get("BlockType") == "WORD":
                text_parts.append(word.get("Text", ""))

            elif (
                word.get("BlockType") == "SELECTION_ELEMENT"
                and word.get("SelectionStatus") == "SELECTED"
            ):
                text_parts.append("X")

    return " ".join(text_parts).strip()


def get_value(key_block, block_map):
    for relationship in key_block.get("Relationships", []):
        if relationship.get("Type") != "VALUE":
            continue

        for value_id in relationship.get("Ids", []):
            value_block = block_map.get(value_id)

            if value_block:
                return get_text(value_block, block_map)

    return ""


def average_block_confidence(blocks):
    values = [
        float(block.get("Confidence"))
        for block in blocks or []
        if block.get("Confidence") is not None
    ]

    if not values:
        return 0

    return round(sum(values) / len(values), 2)


def count_pages(blocks):
    page_blocks = [
        block
        for block in blocks or []
        if block.get("BlockType") == "PAGE"
    ]

    if page_blocks:
        return len(page_blocks)

    page_numbers = {
        block.get("Page")
        for block in blocks or []
        if block.get("Page")
    }

    return len(page_numbers)
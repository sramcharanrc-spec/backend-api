import os
import time

import boto3

from app.config import BUCKET_NAME
from app.intake.excel_processor import process_excel
from app.intake.image_processor import process_image
from app.intake.pdf_processor import process_pdf
from app.intake.text_processor import process_text
from app.intake.textract_service import TextractService
from app.utils.terminal_logger import (
    EMOJI_ERROR,
    EMOJI_FILE,
    EMOJI_PROCESSING,
    log_terminal,
)


s3 = boto3.client("s3")
textract = TextractService()

SUPPORTED_EXCEL_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
}

SUPPORTED_TEXTRACT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
}

SUPPORTED_TEXT_EXTENSIONS = {
    ".txt",
}


def extract_bucket_key(file_path: str):
    """
    Converts:
        s3://bucket/key -> (bucket, key)
    """
    if not file_path:
        raise ValueError("Missing file path")

    if file_path.startswith("s3://"):
        parts = file_path[5:].split("/", 1)

        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid S3 path format: {file_path}")

        return parts[0], parts[1]

    raise ValueError(f"Invalid S3 path: {file_path}")


def resolve_s3_location(
    file_path: str,
    key: str | None = None,
    bucket: str = BUCKET_NAME,
):
    """
    Normalizes file path/key/bucket into a valid S3 bucket and key.
    """
    if key:
        return bucket, key

    return extract_bucket_key(file_path)


def get_extension(key_or_path: str) -> str:
    clean_path = str(key_or_path or "").split("?")[0]
    return os.path.splitext(clean_path)[1].lower()


def build_source_file(
    bucket: str,
    key: str,
    extension: str,
    original_path: str,
    object_meta: dict | None = None,
) -> dict:
    source_file = {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "extension": extension,
        "original_path": original_path,
    }

    if object_meta:
        source_file["object_meta"] = object_meta

    return source_file


def validate_s3_object(bucket: str, key: str) -> dict:
    if not bucket:
        raise ValueError("Missing S3 bucket")

    if not key:
        raise ValueError("Missing S3 key")

    response = s3.head_object(Bucket=bucket, Key=key)
    file_size = response.get("ContentLength", 0)

    if file_size == 0:
        raise ValueError("Empty file")

    return {
        "file_size": file_size,
        "content_type": response.get("ContentType"),
        "etag": response.get("ETag"),
        "last_modified": (
            response.get("LastModified").isoformat()
            if response.get("LastModified")
            else None
        ),
    }


def validate_textract_document(bucket: str, key: str, extension: str) -> dict:
    if extension not in SUPPORTED_TEXTRACT_EXTENSIONS:
        raise ValueError(f"Unsupported Textract file type: {extension}")

    return validate_s3_object(bucket, key)


def attach_intake_metadata(
    payload,
    source_file: dict,
    router_name: str,
    duration_seconds: float,
    object_meta: dict | None = None,
):
    """
    Adds router/source metadata to a claim payload without breaking non-dict chunks.
    """
    if not isinstance(payload, dict):
        return payload

    payload.setdefault("source_file", source_file)
    payload.setdefault("intake", {})
    payload["intake"].update(
        {
            "router": router_name,
            "duration_seconds": duration_seconds,
            "object_meta": object_meta or {},
        }
    )

    return payload


async def route_file(
    file_path: str,
    key: str | None = None,
    bucket: str = BUCKET_NAME,
    claim_id: str = "",
):
    """
    Routes uploaded original files to the correct intake processor.

    Supports:
    - PDF
    - PNG/JPG/JPEG
    - XLS/XLSX/CSV
    - TXT

    Yields:
    - one or more processed claim payloads
    """

    start_time = time.time()

    resolved_bucket, resolved_key = resolve_s3_location(
        file_path=file_path,
        key=key,
        bucket=bucket,
    )

    ext = get_extension(resolved_key)

    log_terminal(f"File type detected for processing: {ext}", EMOJI_FILE)
    log_terminal(
        f"Claim processing started for: {resolved_key}",
        EMOJI_PROCESSING,
    )

    print("\n" + "=" * 80)
    print("🧭 [IntakeRouter] STARTED")
    print(f"📄 Original path: {file_path}")
    print(f"🪣 Bucket: {resolved_bucket}")
    print(f"🔑 Key: {resolved_key}")
    print(f"📎 Extension: {ext}")
    print(f"🧾 Claim ID: {claim_id or 'not provided'}")
    print("=" * 80)

    try:
        object_meta = validate_s3_object(resolved_bucket, resolved_key)
        source_file = build_source_file(
            bucket=resolved_bucket,
            key=resolved_key,
            extension=ext,
            original_path=file_path,
            object_meta=object_meta,
        )

        # -------------------------
        # Excel / CSV
        # -------------------------
        if ext in SUPPORTED_EXCEL_EXTENSIONS:
            print("➡️ Routing to Excel processor...")

            async for chunk in process_excel(
                resolved_bucket,
                resolved_key,
            ):
                duration_seconds = round(time.time() - start_time, 2)

                chunk = attach_intake_metadata(
                    payload=chunk,
                    source_file=source_file,
                    router_name="excel",
                    duration_seconds=duration_seconds,
                    object_meta=object_meta,
                )

                yield chunk

            print("✅ [IntakeRouter] Excel processing completed")

        # -------------------------
        # TXT
        # -------------------------
        elif ext in SUPPORTED_TEXT_EXTENSIONS:
            print("➡️ Routing to Text processor...")

            data = await process_text(
                resolved_bucket,
                resolved_key,
                claim_id=claim_id,
            )

            duration_seconds = round(time.time() - start_time, 2)

            data = attach_intake_metadata(
                payload=data,
                source_file=source_file,
                router_name="text",
                duration_seconds=duration_seconds,
                object_meta=object_meta,
            )

            print("✅ [IntakeRouter] Text processing completed")
            print(f"⏱️ Duration: {duration_seconds}s")

            yield data

        # -------------------------
        # PDF
        # -------------------------
        elif ext == ".pdf":
            print("➡️ Routing to PDF processor...")

            validate_textract_document(
                resolved_bucket,
                resolved_key,
                ext,
            )

            textract_data = await textract.extract(
                resolved_bucket,
                resolved_key,
                ext,
            )

            data = await process_pdf(
                resolved_bucket,
                resolved_key,
                textract_data=textract_data,
                claim_id=claim_id,
            )

            duration_seconds = round(time.time() - start_time, 2)

            data = attach_intake_metadata(
                payload=data,
                source_file=source_file,
                router_name="pdf",
                duration_seconds=duration_seconds,
                object_meta=object_meta,
            )

            print("✅ [IntakeRouter] PDF processing completed")
            print(f"⏱️ Duration: {duration_seconds}s")

            yield data

        # -------------------------
        # Image
        # -------------------------
        elif ext in {".png", ".jpg", ".jpeg"}:
            print("➡️ Routing to Image processor...")

            validate_textract_document(
                resolved_bucket,
                resolved_key,
                ext,
            )

            textract_data = await textract.extract(
                resolved_bucket,
                resolved_key,
                ext,
            )

            data = await process_image(
                resolved_bucket,
                resolved_key,
                textract_data=textract_data,
                claim_id=claim_id,
            )

            duration_seconds = round(time.time() - start_time, 2)

            data = attach_intake_metadata(
                payload=data,
                source_file=source_file,
                router_name="image",
                duration_seconds=duration_seconds,
                object_meta=object_meta,
            )

            print("✅ [IntakeRouter] Image processing completed")
            print(f"⏱️ Duration: {duration_seconds}s")

            yield data

        else:
            log_terminal(f"Unsupported file type: {ext}", EMOJI_ERROR)
            raise ValueError(f"Unsupported file type: {ext}")

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        print("❌ [IntakeRouter] FAILED")
        print(f"❌ Error: {str(error)}")
        print(f"⏱️ Duration before failure: {duration_seconds}s")
        print("=" * 80 + "\n")

        log_terminal(f"File routing failed: {str(error)}", EMOJI_ERROR)
        raise

    finally:
        duration_seconds = round(time.time() - start_time, 2)
        print(f"🏁 [IntakeRouter] FINISHED in {duration_seconds}s")
        print("=" * 80 + "\n")
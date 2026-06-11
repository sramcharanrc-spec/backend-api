# from fastapi import APIRouter, File, Form, HTTPException, UploadFile

# from app.config import BUCKET_NAME
# from app.intake.s3_service import upload_file
# from app.queue.queue_manager import claim_queue
# from app.rcm.pipeline_observability import emit_pipeline_event
# from app.utils.terminal_logger import (
#     EMOJI_ERROR,
#     EMOJI_FILE,
#     EMOJI_QUEUE,
#     EMOJI_START,
#     EMOJI_SUCCESS,
#     EMOJI_UPLOAD,
#     TerminalStepLogger,
#     format_file_size,
#     log_terminal,
# )
# from app.websocket.manager import manager

# router = APIRouter()

# BUCKET = BUCKET_NAME
# ALLOWED_TYPES = [".xlsx", ".xls", ".csv", ".pdf", ".png", ".jpg", ".jpeg"]
# MAX_SIZE_MB = 100


# @router.post("/upload")
# async def upload(
#     file: UploadFile = File(...),
#     processing_mode: str = Form("MANUAL"),
#     upload_session_id: str = Form(""),
#     temp_id: str = Form(""),
# ):
#     terminal = TerminalStepLogger("upload")
#     terminal.log("Incoming upload request", EMOJI_START)

#     try:
#         if not file:
#             terminal.log("No file provided", EMOJI_ERROR)
#             raise HTTPException(status_code=400, detail="No file provided")

#         terminal.log(f"File received: {file.filename}", EMOJI_FILE)
#         await manager.broadcast({
#             "type": "UPLOAD_STARTED",
#             "event": "UPLOAD_STARTED",
#             "filename": file.filename,
#             "processing_mode": processing_mode,
#             "upload_session_id": upload_session_id,
#             "temp_id": temp_id,
#         })
#         ext = f".{file.filename.split('.')[-1].lower()}"
#         terminal.log(f"File extension detected: {ext}", EMOJI_FILE)
#         terminal.log(f"File type: {file.content_type}", EMOJI_FILE)

#         terminal.log("File validation started", EMOJI_FILE)
#         if ext not in ALLOWED_TYPES:
#             unsupported_type = file.content_type or ext
#             terminal.log(f"Unsupported file type: {unsupported_type}", EMOJI_ERROR)
#             raise HTTPException(status_code=400, detail="Invalid file type")

#         contents = await file.read()
#         size_bytes = len(contents)
#         size_mb = size_bytes / (1024 * 1024)
#         terminal.log(f"File size: {format_file_size(size_bytes)}", EMOJI_FILE)

#         if size_mb > MAX_SIZE_MB:
#             terminal.log(
#                 f"File validation failed: {format_file_size(size_bytes)} exceeds {MAX_SIZE_MB} MB",
#                 EMOJI_ERROR,
#             )
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"File too large. Max {MAX_SIZE_MB}MB allowed",
#             )

#         terminal.log("File validation completed", EMOJI_SUCCESS)

#         file.file.seek(0)
#         s3_key = f"uploads/{file.filename}"
#         terminal.log(f"S3 key/path generated: {s3_key}", EMOJI_UPLOAD)

#         terminal.log("Uploading file to S3...", EMOJI_UPLOAD)
#         upload_file(file.file, s3_key, BUCKET)
#         terminal.log("S3 upload successful", EMOJI_SUCCESS)
#         terminal.log(f"S3 path: {s3_key}", EMOJI_SUCCESS)

#         terminal.log("Queueing claim processing job...", EMOJI_QUEUE)
#         job = claim_queue.enqueue(
#             "app.queue.jobs.process_document_job",
#             BUCKET,
#             s3_key,
#             processing_mode,
#             upload_session_id,
#             temp_id,
#             job_timeout=900,
#         )
#         terminal.log(f"Claim processing queued: job_id={job.id}", EMOJI_QUEUE)
#         await manager.broadcast({
#             "type": "UPLOAD_QUEUED",
#             "event": "UPLOAD_QUEUED",
#             "filename": file.filename,
#             "job_id": job.id,
#             "processing_mode": processing_mode,
#             "upload_session_id": upload_session_id,
#             "temp_id": temp_id,
#             "stage": "Intake queued",
#         })
#         await emit_pipeline_event(
#             "UPLOAD_API",
#             "QUEUE",
#             "Upload completed and claim processing queued",
#             metadata={
#                 "filename": file.filename,
#                 "content_type": file.content_type,
#                 "file_size_bytes": size_bytes,
#                 "s3_key": s3_key,
#                 "job_id": job.id,
#                 "upload_session_id": upload_session_id,
#                 "temp_id": temp_id,
#                 "queue": "claims",
#             },
#         )

#         response = {
#             "status": "QUEUED",
#             "file": s3_key,
#             "job_id": job.id,
#             "upload_session_id": upload_session_id,
#             "temp_id": temp_id,
#             "queue": "claims",
#         }
#         terminal.completed("API response returned successfully")
#         return response

#     except Exception as e:
#         terminal.error("upload endpoint", e)
#         log_terminal(f"Total execution time before failure: {terminal.elapsed_seconds():.2f}s", EMOJI_ERROR)
#         if isinstance(e, HTTPException):
#             raise
#         raise HTTPException(status_code=500, detail=str(e))


from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import BUCKET_NAME
from app.intake.s3_service import upload_file
from app.queue.queue_manager import claim_queue
from app.rcm.pipeline_observability import emit_pipeline_event
from app.utils.id_generator import generate_claim_id
from app.utils.terminal_logger import (
    EMOJI_ERROR,
    EMOJI_FILE,
    EMOJI_QUEUE,
    EMOJI_START,
    EMOJI_SUCCESS,
    EMOJI_UPLOAD,
    TerminalStepLogger,
    format_file_size,
    log_terminal,
)
from app.websocket.manager import manager


router = APIRouter()

BUCKET = BUCKET_NAME

ALLOWED_TYPES = {
    ".xlsx",
    ".xls",
    ".csv",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
}

MAX_SIZE_MB = 100


def normalize_processing_mode(value: str | None) -> str:
    mode = str(value or "MANUAL").strip().upper()
    return mode if mode in {"MANUAL", "AUTO"} else "MANUAL"


def safe_upload_result(upload_result, bucket: str, key: str, fallback_size: int) -> dict:
    """
    Supports both old and new upload_file() return styles.

    Old style:
        return key

    New style:
        return {
            "bucket": bucket,
            "key": key,
            "s3_uri": "...",
            "size_bytes": ...
        }
    """
    if isinstance(upload_result, dict):
        return {
            "bucket": upload_result.get("bucket") or bucket,
            "key": upload_result.get("key") or key,
            "s3_uri": upload_result.get("s3_uri") or f"s3://{bucket}/{key}",
            "size_bytes": upload_result.get("size_bytes", fallback_size),
            "duration_seconds": upload_result.get("duration_seconds"),
        }

    return {
        "bucket": bucket,
        "key": str(upload_result or key),
        "s3_uri": f"s3://{bucket}/{str(upload_result or key)}",
        "size_bytes": fallback_size,
        "duration_seconds": None,
    }


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    processing_mode: str = Form("MANUAL"),
    upload_session_id: str = Form(""),
    temp_id: str = Form(""),
):
    claim_id = generate_claim_id()
    processing_mode = normalize_processing_mode(processing_mode)

    terminal = TerminalStepLogger("upload")
    terminal.log("Incoming upload request", EMOJI_START)

    filename = None

    try:
        # ---------------------------------------------------
        # Step 1: Validate uploaded file exists
        # ---------------------------------------------------
        if not file:
            terminal.log("No file provided", EMOJI_ERROR)
            raise HTTPException(status_code=400, detail="No file provided")

        filename = file.filename or ""

        if not filename:
            terminal.log("Uploaded file has no filename", EMOJI_ERROR)
            raise HTTPException(status_code=400, detail="Uploaded file has no filename")

        terminal.log(f"File received: {filename}", EMOJI_FILE)

        await manager.broadcast(
            {
                "type": "UPLOAD_STARTED",
                "event": "UPLOAD_STARTED",
                "claim_id": claim_id,
                "id": claim_id,
                "filename": filename,
                "processing_mode": processing_mode,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
            }
        )

        # ---------------------------------------------------
        # Step 2: Validate extension
        # ---------------------------------------------------
        if "." not in filename:
            terminal.log("File has no extension", EMOJI_ERROR)
            raise HTTPException(status_code=400, detail="File has no extension")

        ext = f".{filename.rsplit('.', 1)[-1].lower()}"

        terminal.log(f"File extension detected: {ext}", EMOJI_FILE)
        terminal.log(f"File type: {file.content_type}", EMOJI_FILE)

        terminal.log("File validation started", EMOJI_FILE)

        if ext not in ALLOWED_TYPES:
            unsupported_type = file.content_type or ext
            terminal.log(f"Unsupported file type: {unsupported_type}", EMOJI_ERROR)

            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid file type",
                    "extension": ext,
                    "allowed_types": sorted(ALLOWED_TYPES),
                },
            )

        # IMPORTANT:
        # Allowing .txt here is only upload-level support.
        # app/intake/router.py must also route .txt files to a text processor.
        if ext == ".txt":
            terminal.log(
                "TXT upload accepted. Ensure app.intake.router supports .txt routing.",
                EMOJI_FILE,
            )

        # ---------------------------------------------------
        # Step 3: Validate file size
        # ---------------------------------------------------
        contents = await file.read()
        size_bytes = len(contents)
        size_mb = size_bytes / (1024 * 1024)

        terminal.log(f"File size: {format_file_size(size_bytes)}", EMOJI_FILE)

        if size_bytes == 0:
            terminal.log("File validation failed: empty file", EMOJI_ERROR)
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        if size_mb > MAX_SIZE_MB:
            terminal.log(
                f"File validation failed: {format_file_size(size_bytes)} exceeds {MAX_SIZE_MB} MB",
                EMOJI_ERROR,
            )
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max {MAX_SIZE_MB}MB allowed",
            )

        terminal.log("File validation completed", EMOJI_SUCCESS)

        # Reset file pointer after reading for size validation.
        file.file.seek(0)

        # ---------------------------------------------------
        # Step 4: Upload original file to S3
        # ---------------------------------------------------
        safe_filename = filename.replace("\\", "_").replace("/", "_")
        s3_key = f"uploads/{safe_filename}"

        terminal.log(f"S3 key/path generated: {s3_key}", EMOJI_UPLOAD)
        terminal.log("Uploading file to S3...", EMOJI_UPLOAD)

        upload_result = upload_file(
            file.file,
            s3_key,
            BUCKET,
            content_type=file.content_type,
        )

        upload_result = safe_upload_result(
            upload_result=upload_result,
            bucket=BUCKET,
            key=s3_key,
            fallback_size=size_bytes,
        )

        source_file = {
            "bucket": upload_result["bucket"],
            "key": upload_result["key"],
            "s3_uri": upload_result["s3_uri"],
            "filename": filename,
            "content_type": file.content_type,
            "extension": ext,
            "size_bytes": upload_result.get("size_bytes", size_bytes),
            "upload_duration_seconds": upload_result.get("duration_seconds"),
        }

        terminal.log("S3 upload successful", EMOJI_SUCCESS)
        terminal.log(f"S3 path: {source_file['s3_uri']}", EMOJI_SUCCESS)

        # ---------------------------------------------------
        # Step 5: Queue background processing
        # ---------------------------------------------------
        terminal.log("Queueing claim processing job...", EMOJI_QUEUE)
        print(f"📌 Enqueueing claim job: claim_id={claim_id}", flush=True)

        job = claim_queue.enqueue(
            "app.queue.jobs.process_document_job",
            source_file["bucket"],
            source_file["key"],
            processing_mode,
            upload_session_id,
            temp_id,
            claim_id,
            job_timeout=900,
        )

        terminal.log(f"Claim processing queued: job_id={job.id}", EMOJI_QUEUE)

        await manager.broadcast(
            {
                "type": "UPLOAD_QUEUED",
                "event": "UPLOAD_QUEUED",
                "claim_id": claim_id,
                "id": claim_id,
                "filename": filename,
                "job_id": job.id,
                "processing_mode": processing_mode,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
                "stage": "Intake queued",
                "source_file": source_file,
            }
        )

        await emit_pipeline_event(
            "UPLOAD_API",
            "QUEUE",
            "Upload completed and claim processing queued",
            metadata={
                "claim_id": claim_id,
                "filename": filename,
                "content_type": file.content_type,
                "file_size_bytes": size_bytes,
                "s3_key": source_file["key"],
                "s3_uri": source_file["s3_uri"],
                "job_id": job.id,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
                "queue": "claims",
            },
        )

        response = {
            "status": "QUEUED",
            "claim_id": claim_id,
            "id": claim_id,
            "file": source_file["key"],
            "source_file": source_file,
            "job_id": job.id,
            "processing_mode": processing_mode,
            "upload_session_id": upload_session_id,
            "temp_id": temp_id,
            "queue": "claims",
        }

        terminal.completed("API response returned successfully")
        return response

    except HTTPException as error:
        await manager.broadcast(
            {
                "type": "UPLOAD_FAILED",
                "event": "UPLOAD_FAILED",
                "claim_id": claim_id,
                "id": claim_id,
                "filename": filename or getattr(file, "filename", None),
                "processing_mode": processing_mode,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
                "status_code": error.status_code,
                "error": error.detail,
            }
        )
        raise

    except Exception as error:
        terminal.error("upload endpoint", error)

        log_terminal(
            f"Total execution time before failure: {terminal.elapsed_seconds():.2f}s",
            EMOJI_ERROR,
        )

        await manager.broadcast(
            {
                "type": "UPLOAD_FAILED",
                "event": "UPLOAD_FAILED",
                "claim_id": claim_id,
                "id": claim_id,
                "filename": filename or getattr(file, "filename", None),
                "processing_mode": processing_mode,
                "upload_session_id": upload_session_id,
                "temp_id": temp_id,
                "error": str(error),
            }
        )

        raise HTTPException(status_code=500, detail=str(error))
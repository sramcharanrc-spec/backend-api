# import boto3

# from app.utils.terminal_logger import (
#     EMOJI_SUCCESS,
#     EMOJI_UPLOAD,
#     log_exception,
#     log_terminal,
# )

# s3 = boto3.client("s3", region_name="us-east-1")


# def upload_file(file_obj, key, bucket):
#     log_terminal(f"Upload started: s3://{bucket}/{key}", EMOJI_UPLOAD)

#     try:
#         s3.upload_fileobj(
#             file_obj,
#             bucket,
#             key,
#             ExtraArgs={"ACL": "bucket-owner-full-control"},
#         )
#         log_terminal(f"Upload completed: s3://{bucket}/{key}", EMOJI_SUCCESS)

#     except Exception as e:
#         log_exception(f"S3 upload: s3://{bucket}/{key}", e)

#     return key


# def download_file(bucket, key, file_path):
#     log_terminal(f"Downloading from S3: s3://{bucket}/{key} -> {file_path}", EMOJI_UPLOAD)

#     try:
#         s3.download_file(bucket, key, file_path)
#         log_terminal(f"S3 download completed: {file_path}", EMOJI_SUCCESS)
#         return file_path
#     except Exception as e:
#         log_exception(f"S3 download: s3://{bucket}/{key}", e)
#         raise

import os
import time
import boto3

from app.utils.terminal_logger import (
    EMOJI_ERROR,
    EMOJI_SUCCESS,
    EMOJI_UPLOAD,
    log_exception,
    log_terminal,
)


AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=AWS_REGION)


def upload_file(file_obj, key, bucket, content_type=None):
    """
    Upload an original file object to S3.

    Returns:
        {
            "bucket": bucket,
            "key": key,
            "s3_uri": "s3://bucket/key",
            "size_bytes": size_bytes,
            "duration_seconds": duration_seconds
        }
    """

    start_time = time.time()

    if not bucket:
        raise ValueError("S3 bucket is required")

    if not key:
        raise ValueError("S3 key is required")

    if file_obj is None:
        raise ValueError("file_obj is required")

    log_terminal(f"Upload started: s3://{bucket}/{key}", EMOJI_UPLOAD)

    try:
        size_bytes = get_file_size(file_obj)

        extra_args = {
            "ACL": "bucket-owner-full-control",
        }

        if content_type:
            extra_args["ContentType"] = content_type

        s3.upload_fileobj(
            file_obj,
            bucket,
            key,
            ExtraArgs=extra_args,
        )

        duration_seconds = round(time.time() - start_time, 2)

        log_terminal(
            f"Upload completed: s3://{bucket}/{key} ({size_bytes} bytes, {duration_seconds}s)",
            EMOJI_SUCCESS,
        )

        return {
            "bucket": bucket,
            "key": key,
            "s3_uri": f"s3://{bucket}/{key}",
            "size_bytes": size_bytes,
            "duration_seconds": duration_seconds,
            "content_type": content_type,
        }

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        log_exception(f"S3 upload failed: s3://{bucket}/{key}", error)
        log_terminal(
            f"S3 upload failed after {duration_seconds}s: s3://{bucket}/{key}",
            EMOJI_ERROR,
        )

        raise


def download_file(bucket, key, file_path):
    """
    Download an original file from S3 to a local temp path.

    Returns the local file path.
    """

    start_time = time.time()

    if not bucket:
        raise ValueError("S3 bucket is required")

    if not key:
        raise ValueError("S3 key is required")

    if not file_path:
        raise ValueError("Local file_path is required")

    log_terminal(
        f"Downloading from S3: s3://{bucket}/{key} -> {file_path}",
        EMOJI_UPLOAD,
    )

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        s3.download_file(bucket, key, file_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Downloaded file not found: {file_path}")

        size_bytes = os.path.getsize(file_path)

        if size_bytes == 0:
            raise ValueError(f"Downloaded file is empty: {file_path}")

        duration_seconds = round(time.time() - start_time, 2)

        log_terminal(
            f"S3 download completed: {file_path} ({size_bytes} bytes, {duration_seconds}s)",
            EMOJI_SUCCESS,
        )

        return file_path

    except Exception as error:
        duration_seconds = round(time.time() - start_time, 2)

        log_exception(f"S3 download failed: s3://{bucket}/{key}", error)
        log_terminal(
            f"S3 download failed after {duration_seconds}s: s3://{bucket}/{key}",
            EMOJI_ERROR,
        )

        raise


def object_exists(bucket, key):
    """
    Check whether an object exists in S3.
    """

    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True

    except Exception:
        return False


def get_object_metadata(bucket, key):
    """
    Return S3 object metadata for debugging and intake tracking.
    """

    response = s3.head_object(Bucket=bucket, Key=key)

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "content_length": response.get("ContentLength", 0),
        "content_type": response.get("ContentType"),
        "etag": response.get("ETag"),
        "last_modified": (
            response.get("LastModified").isoformat()
            if response.get("LastModified")
            else None
        ),
    }


def get_file_size(file_obj):
    """
    Safely get size of file-like object without changing its final read position.
    """

    try:
        current_position = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(current_position)
        return size

    except Exception:
        return None
# app/services/s3_client.py
"""
Minimal stub for S3 client to allow the app to import without boto3.
This backend is configured to run in 'sample-only' dev mode where S3 calls
are not used. If any code attempts to call these functions at runtime,
they will raise a clear error.
"""

def load_ehr_as_rows(key: str, *args, **kwargs):
    """
    Stub loader: raises at runtime to make intent explicit.
    Replace with real S3 logic if you later enable S3.
    """
    raise RuntimeError(
        "S3 functionality is disabled in sample-only mode. "
        "Set up boto3 and restore the real s3_client implementation to enable S3."
    )

def list_s3_keys(prefix: str = ""):
    """Stub list: returns empty list (no S3 objects available)."""
    return []

def get_s3_object(key: str):
    """Stub get: raises to indicate no S3 access."""
    raise RuntimeError("S3 functionality is disabled in sample-only mode.")

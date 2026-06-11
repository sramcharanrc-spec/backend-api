from urllib.parse import parse_qsl, urlsplit, urlunsplit


SENSITIVE_QUERY_KEYS = {
    "X-Amz-Signature",
    "X-Amz-Credential",
    "X-Amz-Security-Token",
    "X-Amz-Algorithm",
    "X-Amz-Date",
    "X-Amz-Expires",
    "X-Amz-SignedHeaders",
    "AWSAccessKeyId",
    "Signature",
    "Expires",
}


SENSITIVE_VALUE_MARKERS = {
    "amazonaws.com",
    "X-Amz-",
    "AWSAccessKeyId",
    "Signature",
}


SENSITIVE_PAYLOAD_KEYS = {
    "presigned_url",
    "signed_url",
    "download_url",
    "file_url",
    "url",
}


def mask_presigned_url(value):
    """
    Removes sensitive query params from presigned S3 URLs.

    Keeps only:
    scheme + host + path

    Example:
    https://bucket.s3.amazonaws.com/file.pdf?X-Amz-Signature=abc
    becomes:
    https://bucket.s3.amazonaws.com/file.pdf
    """

    if not value:
        return value

    text = str(value)

    if "?" not in text:
        return text

    should_mask = any(marker in text for marker in SENSITIVE_VALUE_MARKERS)

    try:
        parts = urlsplit(text)

        query_keys = {
            key
            for key, _ in parse_qsl(parts.query, keep_blank_values=True)
        }

        if query_keys.intersection(SENSITIVE_QUERY_KEYS):
            should_mask = True

        if not should_mask:
            return text

        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            "",
        ))

    except Exception:
        return text.split("?", 1)[0]


def mask_sensitive_payload(value):
    """
    Recursively masks presigned URLs inside dict/list/string payloads.

    This is intended for terminal logs only.
    Do not use this to mutate payloads sent to authenticated frontend users
    if frontend needs the real download URL.
    """

    if isinstance(value, dict):
        masked = {}

        for key, item in value.items():
            normalized_key = str(key).lower()

            if normalized_key in SENSITIVE_PAYLOAD_KEYS:
                masked[key] = mask_presigned_url(item)
            else:
                masked[key] = mask_sensitive_payload(item)

        return masked

    if isinstance(value, list):
        return [
            mask_sensitive_payload(item)
            for item in value
        ]

    if isinstance(value, str):
        return mask_presigned_url(value)

    return value
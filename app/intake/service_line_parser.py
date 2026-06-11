# from __future__ import annotations

# import re
# from collections import defaultdict
# from datetime import datetime
# from typing import Any, Dict, Iterable, List


# CPT_PATTERN = re.compile(r"\b([0-9OISB]{5})\b")
# MONEY_PATTERN = re.compile(r"\$?\b([0-9OISB]{1,4}(?:[,\.][0-9OISB]{2})?)\b")
# DATE_PATTERN = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
# NPI_PATTERN = re.compile(r"\b([0-9OISB]{10})\b")
# MODIFIER_PATTERN = re.compile(r"\b(2[45]|5[79]|[A-Z]{2}|TC|LT|RT)\b")


# def parse_service_lines(textract_or_parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
#     """Extract service rows from Textract blocks using row clustering plus regex fallback."""
#     rows = _cluster_rows(textract_or_parsed)
#     services: List[Dict[str, Any]] = []

#     for row in rows:
#         text = " ".join(item["text"] for item in row["items"])
#         service = _parse_service_text(text)
#         if service:
#             service["row_confidence"] = round(sum(item["confidence"] for item in row["items"]) / max(len(row["items"]), 1), 2)
#             services.append(service)

#     if not services:
#         text = _all_text(textract_or_parsed)
#         services = _regex_fallback(text)

#     return _dedupe_services(_normalize_service(service) for service in services)


# def _cluster_rows(textract_or_parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
#     blocks = textract_or_parsed.get("Blocks", []) if isinstance(textract_or_parsed, dict) else []
#     words = []
#     for block in blocks:
#         if block.get("BlockType") not in {"WORD", "LINE"} or not block.get("Text"):
#             continue
#         box = block.get("Geometry", {}).get("BoundingBox", {})
#         words.append({
#             "text": str(block.get("Text", "")),
#             "top": float(box.get("Top", 0)),
#             "left": float(box.get("Left", 0)),
#             "confidence": float(block.get("Confidence", 80)) / 100,
#         })
#     words.sort(key=lambda item: (round(item["top"], 3), item["left"]))

#     buckets: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
#     for item in words:
#         buckets[int(item["top"] * 100)].append(item)
#     rows = []
#     for _, items in sorted(buckets.items()):
#         items.sort(key=lambda item: item["left"])
#         text = " ".join(item["text"] for item in items).upper()
#         if _row_has_service_signal(text):
#             rows.append({"items": items})
#     return rows


# def _row_has_service_signal(text: str) -> bool:
#     return bool(CPT_PATTERN.search(text)) and (
#         "$" in text
#         or "CHARGE" in text
#         or len(MONEY_PATTERN.findall(text)) >= 2
#         or DATE_PATTERN.search(text)
#     )


# def _parse_service_text(text: str) -> Dict[str, Any] | None:
#     repaired = _repair_ocr_digits(text.upper())
#     cpt_matches = [match.group(1) for match in CPT_PATTERN.finditer(repaired)]
#     cpt = next((code for code in cpt_matches if _looks_like_cpt(code)), None)
#     if not cpt:
#         return None

#     money_values = []
#     for match in MONEY_PATTERN.finditer(repaired):
#         value = _to_float(match.group(1))
#         if value is not None and value >= 1:
#             money_values.append(value)

#     date_match = DATE_PATTERN.search(repaired)
#     npi_match = NPI_PATTERN.search(repaired)
#     modifiers = [m.group(1) for m in MODIFIER_PATTERN.finditer(repaired) if m.group(1) != cpt]
#     units = _infer_units(repaired)
#     charge = money_values[-1] if money_values else 100.0

#     return {
#         "date_of_service": _normalize_date(date_match.group(1)) if date_match else None,
#         "cpt": cpt,
#         "cpt_code": cpt,
#         "modifier": modifiers[0] if modifiers else "",
#         "modifiers": modifiers[:4],
#         "charge": charge,
#         "units": units,
#         "diagnosis_pointer": _diagnosis_pointer(repaired),
#         "rendering_provider_npi": npi_match.group(1) if npi_match else None,
#         "pos": _pos(repaired),
#         "source": "universal_service_line_parser",
#     }


# def _regex_fallback(text: str) -> List[Dict[str, Any]]:
#     repaired = _repair_ocr_digits(text.upper())
#     services = []
#     for match in CPT_PATTERN.finditer(repaired):
#         cpt = match.group(1)
#         if not _looks_like_cpt(cpt):
#             continue
#         window = repaired[max(0, match.start() - 90): match.end() + 130]
#         service = _parse_service_text(window)
#         if service:
#             services.append(service)
#     return services


# def _normalize_service(service: Dict[str, Any]) -> Dict[str, Any]:
#     service = dict(service)
#     service["cpt"] = service.get("cpt") or service.get("cpt_code")
#     service["cpt_code"] = service["cpt"]
#     service["units"] = int(service.get("units") or 1)
#     service["charge"] = float(service.get("charge") or 100)
#     service["confidence"] = min(0.98, max(0.45, service.get("row_confidence", 0.82)))
#     return service


# def _dedupe_services(services: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
#     seen = set()
#     output = []
#     for service in services:
#         key = (service.get("date_of_service"), service.get("cpt"), service.get("charge"))
#         if key in seen:
#             continue
#         seen.add(key)
#         output.append(service)
#     return output


# def _all_text(textract_or_parsed: Dict[str, Any]) -> str:
#     if textract_or_parsed.get("text"):
#         return str(textract_or_parsed["text"])
#     if textract_or_parsed.get("lines"):
#         return "\n".join(str(line) for line in textract_or_parsed["lines"])
#     return "\n".join(str(block.get("Text", "")) for block in textract_or_parsed.get("Blocks", []) if block.get("Text"))


# def _repair_ocr_digits(value: str) -> str:
#     return value.translate(str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8"}))


# def _looks_like_cpt(value: str) -> bool:
#     try:
#         code = int(value)
#     except ValueError:
#         return False
#     return 10000 <= code <= 99999


# def _to_float(value: str) -> float | None:
#     try:
#         cleaned = _repair_ocr_digits(value).replace(",", "")
#         if cleaned.count(".") > 1:
#             cleaned = cleaned.replace(".", "", cleaned.count(".") - 1)
#         return float(cleaned)
#     except Exception:
#         return None


# def _infer_units(text: str) -> int:
#     units_match = re.search(r"\b(?:UNITS?|DAYS?)\s*[:#]?\s*(\d{1,2})\b", text)
#     if units_match:
#         return max(1, int(units_match.group(1)))
#     tail_numbers = [int(item) for item in re.findall(r"\b(\d{1,2})\b", text)]
#     return max(1, tail_numbers[-1]) if tail_numbers and tail_numbers[-1] <= 12 else 1


# def _diagnosis_pointer(text: str) -> str:
#     match = re.search(r"\b(?:DIAG|DX|POINTER)\s*[:#]?\s*([A-L1-4, ]+)", text)
#     return match.group(1).strip() if match else ""


# def _pos(text: str) -> str:
#     match = re.search(r"\bPOS\s*[:#]?\s*(\d{2})\b", text)
#     return match.group(1) if match else ""


# def _normalize_date(value: str) -> str:
#     for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d"):
#         try:
#             return datetime.strptime(value, fmt).date().isoformat()
#         except ValueError:
#             continue
#     return value


from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List


# CPT/HCPCS OCR often confuses letters with digits:
# O -> 0, I -> 1, S -> 5, B -> 8
DIGIT_REPAIR = str.maketrans({
    "O": "0",
    "I": "1",
    "S": "5",
    "B": "8",
})

CPT_PATTERN = re.compile(r"\b([0-9OISB]{5})\b")

# Money is intentionally stricter than the old version.
# This avoids accidentally treating CPT/date fragments as money.
MONEY_PATTERN = re.compile(
    r"(?:\$|\b(?:CHARGE|AMOUNT|BILLED|TOTAL)\b[:\s]*)"
    r"\s*([0-9OISB]{1,4}(?:,[0-9OISB]{3})*(?:\.[0-9OISB]{2})?|[0-9OISB]+(?:\.[0-9OISB]{2})?)",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{4}-\d{2}-\d{2}"
    r")\b"
)

NPI_PATTERN = re.compile(r"\b([0-9OISB]{10})\b")

MODIFIER_PATTERN = re.compile(
    r"\b(2[45]|5[79]|TC|LT|RT|XE|XP|XS|XU|[A-Z]{2})\b"
)


def parse_service_lines(textract_or_parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract service rows from Textract OCR.

    Strategy:
    1. Use geometry-based row clustering from Textract WORD/LINE blocks.
    2. Parse each likely service row.
    3. If no rows are found, scan all OCR text with regex fallback.
    4. Normalize and deduplicate services.
    """

    textract_or_parsed = textract_or_parsed or {}

    rows = _cluster_rows(textract_or_parsed)
    services: List[Dict[str, Any]] = []

    for row in rows:
        text = " ".join(item["text"] for item in row["items"])
        service = _parse_service_text(text)

        if service:
            service["row_confidence"] = round(
                sum(item["confidence"] for item in row["items"])
                / max(len(row["items"]), 1),
                2,
            )
            service["source"] = "service_line_row_cluster"
            services.append(service)

    if not services:
        text = _all_text(textract_or_parsed)
        services = _regex_fallback(text)

    return _dedupe_services(
        _normalize_service(service)
        for service in services
        if service
    )


def _cluster_rows(textract_or_parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Group Textract WORD/LINE blocks into approximate rows using their vertical position.

    Textract provides BoundingBox.Top and BoundingBox.Left values.
    We group nearby Top values to infer rows, then sort each row left-to-right.
    """

    blocks = (
        textract_or_parsed.get("Blocks", [])
        if isinstance(textract_or_parsed, dict)
        else []
    )

    words = []

    for block in blocks:
        if block.get("BlockType") not in {"WORD", "LINE"} or not block.get("Text"):
            continue

        box = block.get("Geometry", {}).get("BoundingBox", {})

        words.append({
            "text": str(block.get("Text", "")),
            "top": float(box.get("Top", 0)),
            "left": float(box.get("Left", 0)),
            "confidence": float(block.get("Confidence", 80)) / 100,
        })

    words.sort(key=lambda item: (item["top"], item["left"]))

    # Bucket by top position. 150 gives a little finer grouping than 100.
    buckets: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for item in words:
        buckets[int(item["top"] * 150)].append(item)

    rows = []

    for _, items in sorted(buckets.items()):
        items.sort(key=lambda item: item["left"])
        text = " ".join(item["text"] for item in items).upper()

        if _row_has_service_signal(text):
            rows.append({"items": items})

    return rows


def _row_has_service_signal(text: str) -> bool:
    """
    A row is likely a service row if it contains a CPT-like code and
    one billing/service indicator.
    """

    repaired = _repair_ocr_digits(text)

    has_cpt = bool(CPT_PATTERN.search(repaired))
    has_charge = "$" in text or any(
        word in text
        for word in ["CHARGE", "AMOUNT", "BILLED", "TOTAL"]
    )
    has_date = bool(DATE_PATTERN.search(text))
    has_service_label = any(
        word in text
        for word in ["CPT", "HCPCS", "PROCEDURE", "DOS", "UNITS", "POS"]
    )

    return has_cpt and (has_charge or has_date or has_service_label)


def _parse_service_text(text: str) -> Dict[str, Any] | None:
    """
    Parse one possible service-line text row.

    Returns None if no valid CPT is found.
    """

    raw_text = text.upper()
    repaired = _repair_ocr_digits(raw_text)

    cpt_matches = [
        match.group(1)
        for match in CPT_PATTERN.finditer(repaired)
    ]

    cpt = next(
        (code for code in cpt_matches if _looks_like_cpt(code)),
        None,
    )

    if not cpt:
        return None

    money_values = []

    for match in MONEY_PATTERN.finditer(repaired):
        value = _to_float(match.group(1))

        if value is not None and value >= 0:
            money_values.append(value)

    date_match = DATE_PATTERN.search(raw_text)
    npi_match = NPI_PATTERN.search(repaired)

    modifiers = [
        modifier
        for modifier in _extract_modifiers(raw_text)
        if modifier != cpt
    ]

    units = _infer_units(repaired)

    # Do not invent a fake charge.
    charge = money_values[-1] if money_values else 0.0

    confidence = 0.85

    if not money_values:
        confidence -= 0.25

    if not date_match:
        confidence -= 0.10

    return {
        "date_of_service": (
            _normalize_date(date_match.group(1))
            if date_match
            else ""
        ),
        "cpt": cpt,
        "cpt_code": cpt,
        "modifier": modifiers[0] if modifiers else "",
        "modifiers": modifiers[:4],
        "charge": charge,
        "units": units,
        "diagnosis_pointer": _diagnosis_pointer(repaired),
        "rendering_provider_npi": (
            _normalize_npi(npi_match.group(1))
            if npi_match
            else None
        ),
        "pos": _pos(repaired),
        "source": "universal_service_line_parser",
        "confidence": round(max(0.35, min(0.98, confidence)), 2),
    }


def _regex_fallback(text: str) -> List[Dict[str, Any]]:
    """
    Fallback parser when geometry-based row clustering finds nothing.
    It scans text windows around each CPT-like code.
    """

    repaired = _repair_ocr_digits((text or "").upper())
    services = []

    for match in CPT_PATTERN.finditer(repaired):
        cpt = match.group(1)

        if not _looks_like_cpt(cpt):
            continue

        window = repaired[
            max(0, match.start() - 90): match.end() + 130
        ]

        service = _parse_service_text(window)

        if service:
            service["source"] = "service_line_regex_fallback"
            services.append(service)

    return services


def _normalize_service(service: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure every service has consistent downstream field names.
    """

    service = dict(service)

    service["cpt"] = service.get("cpt") or service.get("cpt_code")
    service["cpt_code"] = service["cpt"]

    service["units"] = _safe_int(service.get("units"), default=1)
    service["charge"] = _safe_float(service.get("charge"), default=0.0)

    service.setdefault("date", service.get("date_of_service") or "")
    service.setdefault("service_date", service.get("date_of_service") or "")
    service.setdefault("date_of_service", service.get("service_date") or service.get("date") or "")

    base_confidence = service.get("row_confidence", service.get("confidence", 0.82))
    service["confidence"] = round(
        min(0.98, max(0.35, float(base_confidence))),
        2,
    )

    # Mark services missing charge so downstream can route to review if needed.
    service["missing_charge"] = service["charge"] <= 0

    return service


def _dedupe_services(services: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output = []

    for service in services:
        key = (
            service.get("date_of_service"),
            service.get("cpt"),
            service.get("charge"),
            service.get("units"),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(service)

    return output


def _all_text(textract_or_parsed: Dict[str, Any]) -> str:
    if not isinstance(textract_or_parsed, dict):
        return ""

    if textract_or_parsed.get("text"):
        return str(textract_or_parsed["text"])

    if textract_or_parsed.get("lines"):
        return "\n".join(
            str(line)
            for line in textract_or_parsed["lines"]
        )

    return "\n".join(
        str(block.get("Text", ""))
        for block in textract_or_parsed.get("Blocks", [])
        if block.get("Text")
    )


def _repair_ocr_digits(value: str) -> str:
    return str(value or "").translate(DIGIT_REPAIR)


def _looks_like_cpt(value: str) -> bool:
    try:
        code = int(value)
    except ValueError:
        return False

    return 10000 <= code <= 99999


def _to_float(value: str) -> float | None:
    try:
        cleaned = _repair_ocr_digits(value).replace(",", "")

        if cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "", cleaned.count(".") - 1)

        return float(cleaned)

    except Exception:
        return None


def _infer_units(text: str) -> int:
    units_match = re.search(
        r"\b(?:UNITS?|DAYS?|QTY|QUANTITY)\s*[:#]?\s*(\d{1,2})\b",
        text,
    )

    if units_match:
        return max(1, int(units_match.group(1)))

    return 1


def _diagnosis_pointer(text: str) -> str:
    match = re.search(
        r"\b(?:DIAG|DX|POINTER)\s*[:#]?\s*([A-L1-4, ]+)",
        text,
    )

    return match.group(1).strip() if match else ""


def _pos(text: str) -> str:
    match = re.search(r"\bPOS\s*[:#]?\s*(\d{2})\b", text)
    return match.group(1) if match else ""


def _extract_modifiers(text: str) -> List[str]:
    """
    Extract known modifiers while avoiding random two-letter words.
    """
    allowed = {
        "24", "25", "57", "59",
        "TC", "LT", "RT",
        "XE", "XP", "XS", "XU",
        "AA", "AD", "QK", "QX", "QY", "QZ",
        "GY", "GZ", "GA",
    }

    matches = [
        match.group(1)
        for match in MODIFIER_PATTERN.finditer(text)
    ]

    return [
        modifier
        for modifier in matches
        if modifier in allowed
    ]


def _normalize_npi(value: str) -> str | None:
    if not value:
        return None

    repaired = _repair_ocr_digits(value)
    digits = re.sub(r"\D", "", repaired)

    return digits if len(digits) == 10 else None


def _normalize_date(value: str) -> str:
    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return value


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()

        return float(value or default)

    except (TypeError, ValueError):
        return default


def _safe_int(value, default=1):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default
import re
from datetime import datetime
from typing import Any


FIELD_MAP = {
    "Patient Name": "patient.name",
    "Patient": "patient.name",
    "Name": "patient.name",
    "pt name": "patient.name",
    "DOB": "patient.dob",
    "Birth": "patient.dob",
    "Birth Date": "patient.dob",
    "Birthdate": "patient.dob",
    "Date of Birth": "patient.dob",
    "Policy": "insurance.member_id",
    "Policy ID": "insurance.member_id",
    "Member ID": "insurance.member_id",
    "Insurance ID": "insurance.member_id",
    "Provider": "provider.name",
    "Provider Name": "provider.name",
    "NPI": "provider.npi",
    "Provider ID": "provider.npi",
    "Provider NPI": "provider.npi",
    "Payer": "insurance.payer",
    "Insurance": "insurance.payer",
    "Total Charge": "total_charge",
}

def _normalize_key(key: Any) -> str:
    text = str(key or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(" :")


_NORMALIZED_FIELD_MAP = {
    _normalize_key(key): value
    for key, value in FIELD_MAP.items()
}


def _four_digit_year(year: str) -> str:
    if len(year) == 4:
        return year
    number = int(year)
    current_year = datetime.utcnow().year % 100
    century = 2000 if number <= current_year + 5 else 1900
    return str(century + number)


def _valid_date(month: str, day: str, year: str) -> str | None:
    year = _four_digit_year(year)
    try:
        parsed = datetime(int(year), int(month), int(day))
    except ValueError:
        return None
    return parsed.strftime("%m/%d/%Y")


def fix_split_dates(value: Any) -> Any:
    """Recombine OCR-split dates while preserving already valid dates."""
    if value in (None, ""):
        return value

    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            fixed = _valid_date(parts[0], parts[1], parts[2])
            return fixed or value
        return value

    text = str(value).strip()
    if not text:
        return value

    iso_match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso_match:
        year, month, day = iso_match.groups()
        return _valid_date(month, day, year) or text

    separated_match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if separated_match:
        month, day, year = separated_match.groups()
        return _valid_date(month, day, year) or text

    split_match = re.fullmatch(r"(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})", text)
    if split_match:
        fixed = _valid_date(*split_match.groups())
        return fixed or text

    inline_split = re.search(r"\b(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\b", text)
    if inline_split:
        fixed = _valid_date(*inline_split.groups())
        if fixed:
            return text[:inline_split.start()] + fixed + text[inline_split.end():]

    return value


def normalize_fields(fields):

    normalized = {}

    for key, value in (fields or {}).items():

        k = _normalize_key(key)

        if k in _NORMALIZED_FIELD_MAP:
            mapped_key = _NORMALIZED_FIELD_MAP[k]
            normalized[mapped_key] = fix_split_dates(value) if mapped_key == "patient.dob" else value

    return normalized

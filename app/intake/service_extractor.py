# import re

# from app.intake.form_normalizer import fix_split_dates


# CPT_PATTERN = re.compile(r"\b([0-9OISB]{5})\b")
# CHARGE_PATTERN = re.compile(r"\$?\s*([0-9OISB]{1,3}(?:,[0-9OISB]{3})*(?:\.[0-9OISB]{2})?|[0-9OISB]+(?:\.[0-9OISB]{2})?)\b")
# DIGIT_REPAIR = str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8"})


# def extract_services(extracted):

#     services = []

#     # 🔥 Case 1: CPT in keys (your current case)
#     for k, v in extracted.items():

#         # Find CPT in key
#         cpt_match = re.search(r"\b(\d{5})\b", k)

#         # Find amount in value
#         amount_match = re.search(r"\d+\.?\d*", str(v))

#         if cpt_match and amount_match:
#             services.append({
#                 "cpt": cpt_match.group(1),
#                 "cpt_code": cpt_match.group(1),
#                 "charge": float(amount_match.group()),
#                 "units": 1,
#             })

#     # 🔥 Case 2: fallback (full text scan)
#     if not services:
#         full_text = " ".join([str(v) for v in extracted.values()])

#         matches = re.findall(
#             r"(?:CPT[:\s]*)(\d{5}).*?(?:\$?)(\d+\.?\d*)",
#             full_text,
#             re.IGNORECASE
#         )

#         for m in matches:
#             services.append({
#                 "cpt": m[0],
#                 "cpt_code": m[0],
#                 "charge": float(m[1]),
#                 "units": 1,
#             })

#     return services


# def extract_services_from_tables(tables):
#     services = []
#     seen = set()

#     for table in tables or []:
#         for row in _table_rows(table):
#             service = _service_from_row(row)
#             if not service:
#                 continue

#             key = (
#                 service.get("description"),
#                 service.get("cpt"),
#                 service.get("date") or service.get("date_of_service"),
#                 service.get("units"),
#                 service.get("charge"),
#             )
#             if key in seen:
#                 continue
#             seen.add(key)
#             services.append(service)

#     return services


# def _table_rows(table):
#     if isinstance(table, dict):
#         rows = table.get("rows")
#         if isinstance(rows, list):
#             return rows
#         return []

#     rows = getattr(table, "rows", None)
#     return rows if isinstance(rows, list) else []


# def _clean_cell(value):
#     return re.sub(r"\s+", " ", str(value or "")).strip()


# def _repair_digits(value):
#     return str(value or "").upper().translate(DIGIT_REPAIR)


# def _extract_cpt(value):
#     repaired = _repair_digits(value)
#     for match in CPT_PATTERN.finditer(repaired):
#         code = match.group(1)
#         try:
#             numeric = int(code)
#         except ValueError:
#             continue
#         if 10000 <= numeric <= 99999:
#             return code
#     return ""


# def _extract_charge(value):
#     text = _repair_digits(value).replace(" ", "")
#     candidates = []
#     for match in CHARGE_PATTERN.finditer(text):
#         raw = match.group(1).replace(",", "")
#         try:
#             amount = float(raw)
#         except ValueError:
#             continue
#         if amount >= 0:
#             candidates.append(amount)
#     return candidates[-1] if candidates else None


# def _extract_units(value):
#     match = re.search(r"\b(\d{1,3})\b", _repair_digits(value))
#     if not match:
#         return 1
#     return max(1, int(match.group(1)))


# def _is_blank_row(row):
#     return not any(_clean_cell(cell) for cell in row)


# def _is_header_row(row):
#     text = " ".join(_clean_cell(cell) for cell in row).upper()
#     header_terms = ["DESCRIPTION", "CPT", "HCPCS", "SERVICE DATE", "UNITS", "CHARGE"]
#     return any(term in text for term in header_terms) and not _extract_cpt(text)


# def _service_from_row(row):
#     if not isinstance(row, (list, tuple)):
#         return None

#     cells = [_clean_cell(cell) for cell in row]
#     if _is_blank_row(cells) or _is_header_row(cells):
#         return None

#     if len(cells) < 6:
#         return None

#     cpt = _extract_cpt(cells[2])
#     charge = _extract_charge(cells[5])
#     if not cpt or charge is None:
#         return None

#     date = fix_split_dates(cells[3])
#     service = {
#         "description": cells[1],
#         "cpt": cpt,
#         "cpt_code": cpt,
#         "date": date,
#         "date_of_service": date,
#         "units": _extract_units(cells[4]),
#         "charge": charge,
#         "source": "textract_table",
#     }
#     return service


import re
from typing import Any, Dict, List, Optional

from app.intake.form_normalizer import fix_split_dates


# CPT/HCPCS OCR can confuse:
# O -> 0, I -> 1, S -> 5, B -> 8
DIGIT_REPAIR = str.maketrans({
    "O": "0",
    "I": "1",
    "S": "5",
    "B": "8",
})

CPT_PATTERN = re.compile(r"\b([0-9OISB]{5})\b")

CHARGE_PATTERN = re.compile(
    r"\$?\s*("
    r"[0-9OISB]{1,3}(?:,[0-9OISB]{3})*(?:\.[0-9OISB]{2})?"
    r"|"
    r"[0-9OISB]+(?:\.[0-9OISB]{2})?"
    r")\b"
)

DATE_PATTERN = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{1,2}\s+\d{1,2}\s+\d{2,4}"
    r")\b"
)


def extract_services(extracted):
    """
    Extract service lines from Textract key-value fields.

    This handles cases where Textract returns fields like:
    {
        "CPT 99213": "$120.00",
        "Service CPT Code": "99213 Charge: 120"
    }
    """

    services = []
    seen = set()

    # Combine key + value because OCR may place CPT in either side.
    for key, value in (extracted or {}).items():
        combined = f"{key} {value}"

        cpt = _extract_cpt(combined)
        charge = _extract_charge(combined)
        service_date = _extract_date(combined)

        if not cpt or charge is None:
            continue

        service = _build_service(
            cpt=cpt,
            charge=charge,
            units=1,
            service_date=service_date,
            description=str(key),
            source="textract_fields",
        )

        dedupe_key = _service_key(service)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        services.append(service)

    # Fallback: scan all extracted text together.
    if not services:
        full_text = " ".join(
            f"{key} {value}"
            for key, value in (extracted or {}).items()
        )

        services.extend(_services_from_text(full_text, source="textract_fields_text"))

    return services


def extract_services_from_tables(tables):
    """
    Extract service lines from Textract table rows.

    Supports:
    - fixed column tables
    - dynamic header-based tables
    - sparse rows where CPT/date/charge appear in different columns
    """

    services = []
    seen = set()

    for table_index, table in enumerate(tables or []):
        rows = _table_rows(table)
        header_map = {}

        for row_index, row in enumerate(rows):
            cells = [_clean_cell(cell) for cell in row]

            if _is_blank_row(cells):
                continue

            if _is_header_row(cells):
                header_map = _header_map(cells)
                continue

            service = _service_from_row(
                cells,
                header_map=header_map,
                table_index=table_index,
                row_index=row_index,
            )

            if not service:
                continue

            key = _service_key(service)

            if key in seen:
                continue

            seen.add(key)
            services.append(service)

    return services


def _services_from_text(text: str, source: str) -> List[Dict[str, Any]]:
    """
    Fallback text scanner.

    Looks for text patterns like:
    CPT: 99213 Charge: 120.00
    99213 Office Visit $120.00
    """

    services = []
    seen = set()

    if not text:
        return services

    # Pattern 1: CPT label followed by charge.
    labeled_matches = re.findall(
        r"(?:CPT|HCPCS|PROCEDURE|PROC)[:\s#]*([0-9OISB]{5}).{0,80}?\$?\s*([0-9OISB,]+(?:\.[0-9OISB]{2})?)",
        text,
        re.IGNORECASE,
    )

    for cpt_raw, charge_raw in labeled_matches:
        cpt = _extract_cpt(cpt_raw)
        charge = _extract_charge(charge_raw)

        if not cpt or charge is None:
            continue

        service = _build_service(
            cpt=cpt,
            charge=charge,
            units=1,
            service_date=_extract_date(text),
            description="Extracted from text",
            source=source,
        )

        key = _service_key(service)

        if key not in seen:
            seen.add(key)
            services.append(service)

    # Pattern 2: any CPT-like code near a money amount.
    if not services:
        for match in CPT_PATTERN.finditer(_repair_digits(text)):
            window = text[max(0, match.start() - 60): match.end() + 100]
            cpt = _extract_cpt(match.group(1))
            charge = _extract_charge(window)

            if not cpt or charge is None:
                continue

            service = _build_service(
                cpt=cpt,
                charge=charge,
                units=1,
                service_date=_extract_date(window),
                description="Extracted from text window",
                source=source,
            )

            key = _service_key(service)

            if key not in seen:
                seen.add(key)
                services.append(service)

    return services


def _service_from_row(
    row: List[str],
    header_map: Optional[Dict[str, int]] = None,
    table_index: int = 0,
    row_index: int = 0,
):
    """
    Convert one table row into a service line.

    First tries header-based extraction.
    Then falls back to scanning the entire row.
    """

    if not isinstance(row, (list, tuple)):
        return None

    cells = [_clean_cell(cell) for cell in row]

    if _is_blank_row(cells) or _is_header_row(cells):
        return None

    header_map = header_map or {}

    # Header-based extraction if table headers are known.
    cpt = _value_by_header(cells, header_map, ["cpt", "hcpcs", "procedure", "proc"])
    charge_text = _value_by_header(cells, header_map, ["charge", "amount", "billed"])
    units_text = _value_by_header(cells, header_map, ["units", "qty", "quantity"])
    date_text = _value_by_header(cells, header_map, ["date", "dos", "service date"])
    description = _value_by_header(cells, header_map, ["description", "desc", "service"])

    # Fallback scan across all cells.
    joined = " ".join(cells)

    cpt = _extract_cpt(cpt or joined)
    charge = _extract_charge(charge_text or joined)
    units = _extract_units(units_text or joined)
    service_date = fix_split_dates(_extract_date(date_text or joined))

    if not description:
        description = _guess_description(cells, cpt)

    if not cpt or charge is None:
        return None

    return _build_service(
        cpt=cpt,
        charge=charge,
        units=units,
        service_date=service_date,
        description=description,
        source="textract_table",
        table_index=table_index,
        row_index=row_index,
    )


def _header_map(cells: List[str]) -> Dict[str, int]:
    """
    Build a header-name to column-index map.

    Example:
    ['Date', 'Description', 'CPT', 'Units', 'Charge']
    =>
    {'date': 0, 'description': 1, 'cpt': 2, 'units': 3, 'charge': 4}
    """

    mapping = {}

    for index, cell in enumerate(cells):
        normalized = _normalize_header(cell)

        if not normalized:
            continue

        mapping[normalized] = index

    return mapping


def _normalize_header(value: str) -> str:
    text = _clean_cell(value).lower()

    if "cpt" in text or "hcpcs" in text:
        return "cpt"

    if "procedure" in text or text == "proc":
        return "procedure"

    if "charge" in text or "amount" in text or "billed" in text:
        return "charge"

    if "unit" in text or "qty" in text or "quantity" in text:
        return "units"

    if "date" in text or text == "dos":
        return "date"

    if "description" in text or "desc" in text or "service" in text:
        return "description"

    return text


def _value_by_header(cells: List[str], header_map: Dict[str, int], names: List[str]) -> str:
    for name in names:
        normalized_name = _normalize_header(name)
        index = header_map.get(normalized_name)

        if index is not None and index < len(cells):
            return cells[index]

    return ""


def _table_rows(table):
    if isinstance(table, dict):
        rows = table.get("rows")

        if isinstance(rows, list):
            return rows

        return []

    rows = getattr(table, "rows", None)

    return rows if isinstance(rows, list) else []


def _clean_cell(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _repair_digits(value):
    return str(value or "").upper().translate(DIGIT_REPAIR)


def _extract_cpt(value):
    """
    Extract a valid 5-digit CPT/HCPCS-style code.
    Repairs common OCR digit mistakes.
    """
    repaired = _repair_digits(value)

    for match in CPT_PATTERN.finditer(repaired):
        code = match.group(1)

        try:
            numeric = int(code)
        except ValueError:
            continue

        # Avoid obvious invalid values.
        if 10000 <= numeric <= 99999:
            return code

    return ""


def _extract_charge(value):
    """
    Extract the last valid money-looking amount from text.
    Last amount is often the line charge in OCR rows.
    """
    text = _repair_digits(value).replace(" ", "")
    candidates = []

    for match in CHARGE_PATTERN.finditer(text):
        raw = match.group(1).replace(",", "")

        try:
            amount = float(raw)
        except ValueError:
            continue

        if amount >= 0:
            candidates.append(amount)

    return candidates[-1] if candidates else None


def _extract_units(value):
    match = re.search(r"\b(\d{1,3})\b", _repair_digits(value))

    if not match:
        return 1

    return max(1, int(match.group(1)))


def _extract_date(value):
    match = DATE_PATTERN.search(str(value or ""))

    if not match:
        return ""

    return fix_split_dates(match.group(1))


def _guess_description(cells: List[str], cpt: str) -> str:
    for cell in cells:
        cleaned = _clean_cell(cell)

        if not cleaned:
            continue

        if cpt and cpt in cleaned:
            continue

        if _extract_charge(cleaned) is not None:
            continue

        if _extract_units(cleaned) != 1 and len(cleaned) <= 3:
            continue

        return cleaned

    return ""


def _is_blank_row(row):
    return not any(_clean_cell(cell) for cell in row)


def _is_header_row(row):
    text = " ".join(_clean_cell(cell) for cell in row).upper()

    header_terms = [
        "DESCRIPTION",
        "CPT",
        "HCPCS",
        "SERVICE DATE",
        "DATE OF SERVICE",
        "DOS",
        "UNITS",
        "QTY",
        "CHARGE",
        "AMOUNT",
        "BILLED",
    ]

    return any(term in text for term in header_terms) and not _extract_cpt(text)


def _build_service(
    cpt,
    charge,
    units=1,
    service_date="",
    description="",
    source="unknown",
    table_index=None,
    row_index=None,
):
    service = {
        "description": description,
        "cpt": cpt,
        "cpt_code": cpt,
        "service_date": service_date,
        "date": service_date,
        "date_of_service": service_date,
        "units": units,
        "charge": charge,
        "source": source,
        "confidence": 0.85 if cpt and charge is not None else 0.55,
    }

    if table_index is not None:
        service["table_index"] = table_index

    if row_index is not None:
        service["row_index"] = row_index

    return service


def _service_key(service):
    return (
        service.get("description"),
        service.get("cpt"),
        service.get("service_date") or service.get("date") or service.get("date_of_service"),
        service.get("units"),
        service.get("charge"),
    )
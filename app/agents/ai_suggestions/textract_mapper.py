import re
from typing import Any, Dict, Iterable, List


def _blocks(textract_output: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if isinstance(textract_output, dict):
        return textract_output.get("Blocks") or textract_output.get("blocks") or []
    return []


def _text_lines(textract_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = []
    for block in _blocks(textract_output):
        block_type = block.get("BlockType") or block.get("block_type")
        if block_type in {"LINE", "WORD"}:
            lines.append({
                "text": block.get("Text", ""),
                "confidence": float(block.get("Confidence") or 0),
                "page": block.get("Page") or 1,
                "raw": block,
            })
    return lines


def _find(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else default


def _codes(pattern: str, text: str) -> List[str]:
    return sorted(set(re.findall(pattern, text, flags=re.IGNORECASE)))


def _extract_services(text: str) -> List[Dict[str, Any]]:
    services = []
    for cpt in _codes(r"\b\d{5}\b", text):
        services.append({"cpt": cpt, "units": 1, "charge": 0.0})
    return services


def map_textract_to_claim(textract_output: Dict[str, Any], claim_id: str = "UNKNOWN") -> Dict[str, Any]:
    lines = _text_lines(textract_output)
    full_text = "\n".join(line["text"] for line in lines)
    cpt_codes = _codes(r"\b\d{5}\b", full_text)
    icd_codes = _codes(r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b", full_text)
    npi = _find(r"\bNPI[:\s#-]*([0-9]{10})\b", full_text)
    dob = _find(r"\bDOB[:\s#-]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", full_text)
    payer = _find(r"\b(?:Payer|Insurance)[:\s#-]*([A-Za-z0-9 &.-]{3,60})", full_text, "UNKNOWN_PAYER")
    provider_name = _find(r"\bProvider[:\s#-]*([A-Za-z .'-]{3,60})", full_text)
    patient_name = _find(r"\bPatient[:\s#-]*([A-Za-z .'-]{3,60})", full_text, "Unknown")

    confidence_values = [line["confidence"] for line in lines if line["confidence"]]
    extraction_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0

    return {
        "claim_id": claim_id,
        "patient": {"name": patient_name, "dob": dob},
        "provider": {"name": provider_name, "npi": npi},
        "payer": {"name": payer},
        "cpt_codes": cpt_codes,
        "icd_codes": icd_codes,
        "services": _extract_services(full_text),
        "extraction": {
            "confidence": extraction_confidence,
            "entities": [
                {"entity_type": "LINE", **line}
                for line in lines
            ],
            "tables_detected": any((block.get("BlockType") or block.get("block_type")) == "TABLE" for block in _blocks(textract_output)),
            "forms_detected": any((block.get("BlockType") or block.get("block_type")) == "KEY_VALUE_SET" for block in _blocks(textract_output)),
        },
    }

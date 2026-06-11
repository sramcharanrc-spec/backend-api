from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, List


def detect_document_type(textract_text: Any) -> str:
    """
    Detect the core claim document type from raw Textract text.

    Returns:
    - CMS1500
    - UB04
    - EOB_ERA
    - INSURANCE_CARD
    - GENERIC

    Important:
    EOB/ERA denial documents must be detected before CMS1500 because
    they often contain claim-like fields such as Member ID, Payer, CPT,
    ICD, and service dates.
    """
    start_time = time.time()

    raw_text = _to_text(textract_text)
    text = raw_text.upper()
    lines = text.splitlines()

    print("\n" + "-" * 80)
    print("🧾 [FormClassifier] detect_document_type STARTED")
    print(f"📄 Text length: {len(text)}")

    cms1500_indicators = [
        "HEALTH INSURANCE CLAIM FORM",
        "CMS-1500",
        "CMS 1500",
        "NUCC",
        "HCFA",
        "PLACE OF SERVICE",
        "DIAGNOSIS POINTER",
        "DAYS OR UNITS",
    ]

    ub04_indicators = [
        "UB-04",
        "UB04",
        "CMS-1450",
        "CMS 1450",
        "TYPE OF BILL",
        "REV CD",
        "REVENUE CODE",
        "STATEMENT COVERS PERIOD",
        "ADMIT DATE",
        "DISCHARGE DATE",
    ]

    eob_era_strong_indicators = [
        "EOB",
        "ERA",
        "EXPLANATION OF BENEFITS",
        "ELECTRONIC REMITTANCE ADVICE",
        "REMITTANCE ADVICE",
        "CLAIM ADJUSTMENT REASON CODE",
        "REMITTANCE ADVICE REMARK CODE",
        "DENIAL CODE",
        "DENIAL REASON",
        "DENIED: YES",
        "DENIED YES",
        "CARC",
        "RARC",
        "835",
    ]

    eob_era_payment_indicators = [
        "CLAIM PAYMENT",
        "PAYMENT AMOUNT",
        "PAID AMOUNT",
        "ALLOWED AMOUNT",
        "PATIENT RESPONSIBILITY",
        "ADJUSTMENT AMOUNT",
        "COINSURANCE",
        "DEDUCTIBLE",
        "COPAY",
    ]

    insurance_card_indicators = [
        "INSURANCE CARD",
        "MEMBER CARD",
        "RXBIN",
        "RXPCN",
        "RXGRP",
        "COPAY",
        "MEDICAL PLAN",
        "GROUP NUMBER",
        "MEMBER ID",
    ]

    # -------------------------------------------------
    # Score signals
    # -------------------------------------------------
    scores = {
        "CMS1500": 0,
        "UB04": 0,
        "EOB_ERA": 0,
        "INSURANCE_CARD": 0,
    }

    for indicator in cms1500_indicators:
        if indicator in text:
            scores["CMS1500"] += 10

    for indicator in ub04_indicators:
        if indicator in text:
            scores["UB04"] += 12

    for indicator in eob_era_strong_indicators:
        if indicator in text:
            scores["EOB_ERA"] += 20

    for indicator in eob_era_payment_indicators:
        if indicator in text:
            scores["EOB_ERA"] += 8

    for indicator in insurance_card_indicators:
        if indicator in text:
            scores["INSURANCE_CARD"] += 6

    # -------------------------------------------------
    # Regex boosts
    # -------------------------------------------------
    if re.search(r"\bCO-\d{2,3}\b", text):
        scores["EOB_ERA"] += 25

    if re.search(r"\bPR-\d{1,3}\b", text):
        scores["EOB_ERA"] += 15

    if re.search(r"\bOA-\d{1,3}\b", text):
        scores["EOB_ERA"] += 15

    if re.search(r"\bPI-\d{1,3}\b", text):
        scores["EOB_ERA"] += 15

    if re.search(r"\bN\d{3,4}\b", text) and ("RARC" in text or "CARC" in text):
        scores["EOB_ERA"] += 15

    if re.search(r"\bDENIED\s*:\s*YES\b", text):
        scores["EOB_ERA"] += 30

    if re.search(r"\bDENIAL\s+CODE\s*:\s*[A-Z]{1,3}-?\d{1,4}\b", text):
        scores["EOB_ERA"] += 30

    if re.search(r"\bCPT\s+CODES?\s*:\s*[\d,\s]+", text):
        scores["EOB_ERA"] += 10

    if re.search(r"\bICD\s+CODES?\s*:\s*[A-Z0-9.,\s]+", text):
        scores["EOB_ERA"] += 10

    # Service grid is useful, but should not beat strong EOB denial evidence.
    looks_like_grid = _looks_like_service_grid(lines)
    if looks_like_grid:
        scores["CMS1500"] += 12

    # -------------------------------------------------
    # Explicit high-priority overrides
    # -------------------------------------------------

    # 1. EOB/ERA denial override
    # This fixes files containing:
    # Denied: Yes
    # Denial Code: CO-197
    # CARC / RARC: CO-197 / N382
    has_denial_code = bool(re.search(r"\bDENIAL\s+CODE\s*:", text))
    has_denied_yes = bool(re.search(r"\bDENIED\s*:\s*YES\b", text))
    has_carc_or_rarc = "CARC" in text or "RARC" in text
    has_adjustment_code = bool(re.search(r"\b(CO|PR|OA|PI)-\d{1,4}\b", text))
    has_eob_label = (
        "EOB" in text
        or "ERA" in text
        or "EXPLANATION OF BENEFITS" in text
        or "REMITTANCE ADVICE" in text
    )

    cms_title_present = (
        "CMS1500" in text
        or "CMS-1500" in text
        or "CMS 1500" in text
        or "HEALTH INSURANCE CLAIM FORM" in text
        or "HCFA" in text
        or "NUCC" in text
    )

    service_grid_present = (
        _looks_like_service_grid(lines)
        or (
            "CPT" in text
            and "ICD" in text
            and "DATE OF SERVICE" in text
            and "POS" in text
            and "CHARGE" in text
        )
    )

    explicit_eob_label = (
        "EXPLANATION OF BENEFITS" in text
        or "ELECTRONIC REMITTANCE ADVICE" in text
        or "REMITTANCE ADVICE" in text
        or re.search(r"\bEOB\b", text)
        or re.search(r"\bERA\b", text)
    )

    strong_eob_denial = (
        bool(re.search(r"\bDENIED\s*:\s*YES\b", text))
        or bool(re.search(r"\bDENIAL\s+CODE\s*:\s*[A-Z]{1,3}-?\d{1,4}\b", text))
    )

    carc_rarc_only = has_carc_or_rarc and has_adjustment_code

    # EOB/ERA override should not steal CMS1500 claims that contain denial-risk hints.
    if explicit_eob_label or strong_eob_denial:
        result = "EOB_ERA"

    elif carc_rarc_only and not cms_title_present and not service_grid_present:
        result = "EOB_ERA"

    elif cms_title_present or service_grid_present:
        result = "CMS1500"    

    # 2. UB04 should beat generic CMS claim language when institutional fields exist.
    elif scores["UB04"] >= 12 and scores["UB04"] >= scores["CMS1500"]:
        result = "UB04"

    # 3. Insurance card detection.
    elif (
        scores["INSURANCE_CARD"] >= 18
        and scores["CMS1500"] < 15
        and scores["EOB_ERA"] < 20
    ):
        result = "INSURANCE_CARD"

    # 4. CMS1500.
    elif scores["CMS1500"] > 0:
        result = "CMS1500"

    # 5. EOB/ERA fallback if enough softer EOB signals exist.
    elif scores["EOB_ERA"] >= 25:
        result = "EOB_ERA"

    else:
        result = "GENERIC"

    duration_seconds = round(time.time() - start_time, 2)

    print(f"📊 Document scores: {scores}")
    print(f"✅ Detected document type: {result}")
    print(f"⏱️ Detection duration: {duration_seconds}s")
    print("-" * 80 + "\n")

    return result


def classify_form(textract_or_parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify healthcare claim form layouts using keyword signals and layout hints.

    Returns:
    - form_type
    - document_type
    - confidence
    - layout_version
    - signals
    - scores
    - duration_seconds

    Important:
    EOB/ERA denial files can contain claim-like fields such as Member ID,
    Payer, CPT, ICD, Service Date, and Claim Amount. Strong denial evidence
    must override CMS1500-style service grid signals.
    """
    start_time = time.time()

    print("\n" + "-" * 80)
    print("🧾 [FormClassifier] classify_form STARTED")

    lines = _lines(textract_or_parsed)
    text = " ".join(lines).upper()
    detected_type = detect_document_type(text)

    print(f"📄 Line count: {len(lines)}")
    print(f"📄 Text length: {len(text)}")
    print(f"📌 Basic detected type: {detected_type}")

    signals: List[str] = []

    scores = {
        "CMS1500": 0,
        "UB04": 0,
        "EOB_ERA": 0,
        "INSURANCE_CARD": 0,
        "REIMBURSEMENT": 0,
        "PRIOR_AUTHORIZATION": 0,
        "PAYER_FORM": 0,
        "CUSTOM": 8,
    }

    term_groups = {
        "CMS1500": {
            "weight": 22,
            "terms": [
                "CMS-1500",
                "CMS 1500",
                "HEALTH INSURANCE CLAIM FORM",
                "NUCC",
                "HCFA",
                "24A",
                "24B",
                "24D",
                "DAYS OR UNITS",
                "DIAGNOSIS POINTER",
            ],
        },
        "UB04": {
            "weight": 18,
            "terms": [
                "UB-04",
                "UB04",
                "CMS-1450",
                "CMS 1450",
                "TYPE OF BILL",
                "REV CD",
                "REVENUE CODE",
                "ADMISSION DATE",
                "ADMIT DATE",
                "DISCHARGE DATE",
                "STATEMENT COVERS PERIOD",
            ],
        },
        "EOB_ERA": {
            "weight": 18,
            "terms": [
                "EOB",
                "ERA",
                "EXPLANATION OF BENEFITS",
                "ELECTRONIC REMITTANCE ADVICE",
                "REMITTANCE ADVICE",
                "CLAIM ADJUSTMENT REASON CODE",
                "REMITTANCE ADVICE REMARK CODE",
                "CLAIM PAYMENT",
                "PAYMENT AMOUNT",
                "PAID AMOUNT",
                "ALLOWED AMOUNT",
                "ADJUSTMENT AMOUNT",
                "PATIENT RESPONSIBILITY",
                "DENIED",
                "DENIED: YES",
                "DENIAL CODE",
                "DENIAL REASON",
                "CARC",
                "RARC",
                "835",
            ],
        },
        "INSURANCE_CARD": {
            "weight": 16,
            "terms": [
                "INSURANCE CARD",
                "MEMBER CARD",
                "MEMBER ID",
                "GROUP NUMBER",
                "RXBIN",
                "RXPCN",
                "RXGRP",
                "COPAY",
                "MEDICAL PLAN",
            ],
        },
        "REIMBURSEMENT": {
            "weight": 14,
            "terms": [
                "REIMBURSEMENT",
                "EXPENSE",
                "PATIENT PAID",
                "RECEIPT",
                "CLAIM REIMBURSEMENT",
            ],
        },
        "PRIOR_AUTHORIZATION": {
            "weight": 18,
            "terms": [
                "PRIOR AUTHORIZATION",
                "PREAUTHORIZATION",
                "PRE AUTH",
                "AUTH REQUEST",
                "AUTHORIZATION REQUEST",
                "REFERRAL REQUEST",
            ],
        },
        "PAYER_FORM": {
            "weight": 8,
            "terms": [
                "PAYER",
                "PLAN",
                "MEMBER ID",
                "GROUP NUMBER",
                "AUTHORIZATION",
            ],
        },
    }

    for candidate_type, config in term_groups.items():
        for term in config["terms"]:
            if term in text:
                scores[candidate_type] += config["weight"]
                signals.append(term)

    # -------------------------------------------------
    # Regex boosts for denial/EOB/ERA evidence
    # -------------------------------------------------
    if re.search(r"\bDENIED\s*:\s*YES\b", text):
        scores["EOB_ERA"] += 35
        signals.append("denied yes")

    if re.search(r"\bDENIAL\s+CODE\s*:\s*[A-Z]{1,3}-?\d{1,4}\b", text):
        scores["EOB_ERA"] += 35
        signals.append("denial code")

    if re.search(r"\b(CO|PR|OA|PI)-\d{1,4}\b", text):
        scores["EOB_ERA"] += 25
        signals.append("adjustment reason code")

    if re.search(r"\bN\d{3,4}\b", text) and ("RARC" in text or "CARC" in text):
        scores["EOB_ERA"] += 15
        signals.append("remark code")

    if "CARC" in text and "RARC" in text:
        scores["EOB_ERA"] += 25
        signals.append("CARC/RARC")

    if "AUTHORIZATION WAS NOT OBTAINED" in text:
        scores["EOB_ERA"] += 20
        scores["PRIOR_AUTHORIZATION"] += 10
        signals.append("authorization not obtained")

    if "PRECERTIFICATION" in text and "ABSENT" in text:
        scores["EOB_ERA"] += 20
        scores["PRIOR_AUTHORIZATION"] += 10
        signals.append("precertification absent")

    # -------------------------------------------------
    # Layout hints
    # -------------------------------------------------
    service_grid = _looks_like_service_grid(lines)
    institutional_grid = _looks_like_institutional_grid(lines)
    insurance_card_layout = _looks_like_insurance_card(lines)

    has_strong_eob_denial = (
        detected_type == "EOB_ERA"
        or bool(re.search(r"\bDENIED\s*:\s*YES\b", text))
        or bool(re.search(r"\bDENIAL\s+CODE\s*:", text))
        or ("CARC" in text and "RARC" in text)
        or bool(re.search(r"\b(CO|PR|OA|PI)-\d{1,4}\b", text))
    )

    # Service grids usually indicate CMS1500, but not when strong denial/EOB evidence exists.
    if service_grid and not has_strong_eob_denial:
        scores["CMS1500"] += 18
        scores["CUSTOM"] += 6
        signals.append("service-line grid")
    elif service_grid and has_strong_eob_denial:
        scores["EOB_ERA"] += 10
        signals.append("claim/service fields inside EOB")

    if institutional_grid:
        scores["UB04"] += 18
        signals.append("institutional revenue-code grid")

    if insurance_card_layout and not has_strong_eob_denial:
        scores["INSURANCE_CARD"] += 18
        signals.append("insurance-card layout")

    # -------------------------------------------------
    # Select form type
    # -------------------------------------------------
    form_type = max(scores, key=scores.get)
    raw_score = scores[form_type]
    confidence = _score_to_confidence(raw_score)

    if confidence < 0.4:
        form_type = "CUSTOM"

    # Hard override: detected EOB/ERA should stay EOB/ERA.
    cms_title_present = (
        "CMS1500" in text
        or "CMS-1500" in text
        or "CMS 1500" in text
        or "HEALTH INSURANCE CLAIM FORM" in text
        or "HCFA" in text
        or "NUCC" in text
    )

    service_grid_present = (
        service_grid
        or (
            "CPT" in text
            and "ICD" in text
            and "DATE OF SERVICE" in text
            and "POS" in text
            and "CHARGE" in text
        )
    )

    if detected_type == "EOB_ERA" and not cms_title_present and not service_grid_present:
        form_type = "EOB_ERA"
        confidence = max(confidence, 0.9)

    elif cms_title_present or service_grid_present:
        form_type = "CMS1500"
        confidence = max(confidence, 0.9)

    elif detected_type in {"CMS1500", "UB04", "INSURANCE_CARD"}:
        detected_score = scores.get(detected_type, 0)

        if detected_score >= 16 or detected_type in {"CMS1500", "UB04"}:
            form_type = detected_type
            confidence = max(confidence, 0.85)

    duration_seconds = round(time.time() - start_time, 2)

    result = {
        "form_type": form_type,
        "document_type": detected_type,
        "confidence": round(confidence, 2),
        "layout_version": _layout_version(textract_or_parsed, form_type),
        "signals": list(dict.fromkeys(signals))[:12],
        "scores": scores,
        "line_count": len(lines),
        "text_length": len(text),
        "duration_seconds": duration_seconds,
    }

    print("✅ [FormClassifier] classify_form COMPLETED")
    print(f"📌 Form type: {result['form_type']}")
    print(f"📌 Document type: {result['document_type']}")
    print(f"📊 Confidence: {result['confidence']}")
    print(f"🔎 Signals: {result['signals']}")
    print(f"📊 Scores: {result['scores']}")
    print(f"⏱️ Duration: {duration_seconds}s")
    print("-" * 80 + "\n")

    return result


def _to_text(textract_text: Any) -> str:
    if isinstance(textract_text, list):
        return " ".join(str(item) for item in textract_text)

    if isinstance(textract_text, dict):
        if textract_text.get("text"):
            return str(textract_text.get("text"))

        if textract_text.get("lines"):
            return " ".join(str(line) for line in textract_text.get("lines", []))

        return " ".join(
            str(block.get("Text", ""))
            for block in textract_text.get("Blocks", [])
            if block.get("BlockType") == "LINE" and block.get("Text")
        )

    return str(textract_text or "")


def _lines(textract_or_parsed: Dict[str, Any]) -> List[str]:
    if not isinstance(textract_or_parsed, dict):
        return []

    if textract_or_parsed.get("lines"):
        return [str(line) for line in textract_or_parsed.get("lines", [])]

    if textract_or_parsed.get("text"):
        return str(textract_or_parsed.get("text")).splitlines()

    return [
        str(block.get("Text", ""))
        for block in textract_or_parsed.get("Blocks", [])
        if block.get("BlockType") == "LINE" and block.get("Text")
    ]





def _looks_like_service_grid(lines: Iterable[str]) -> bool:
    joined = " ".join(lines).upper()

    has_cpt = any(
        token in joined
        for token in ["CPT", "HCPCS", "PROCEDURE", "PROC"]
    )

    has_charge = any(
        token in joined
        for token in ["CHARGE", "AMOUNT", "$"]
    )

    has_dos = any(
        token in joined
        for token in ["DATE OF SERVICE", "DOS", "SERVICE DATE"]
    )

    return (has_cpt and has_charge) or (has_dos and has_charge)


def _looks_like_institutional_grid(lines: Iterable[str]) -> bool:
    joined = " ".join(lines).upper()

    has_rev = any(
        token in joined
        for token in ["REV CD", "REVENUE CODE", "REV CODE"]
    )

    has_units = any(
        token in joined
        for token in ["UNITS", "SERVICE UNITS"]
    )

    has_charges = any(
        token in joined
        for token in ["TOTAL CHARGES", "NON-COVERED CHARGES", "CHARGES"]
    )

    return has_rev and (has_units or has_charges)


def _looks_like_insurance_card(lines: Iterable[str]) -> bool:
    joined = " ".join(lines).upper()

    has_card_text = "INSURANCE CARD" in joined or "ID CARD" in joined
    has_rx = any(token in joined for token in ["RXBIN", "RXPCN", "RXGRP"])
    has_copay = "COPAY" in joined
    has_member = "MEMBER ID" in joined or "ID #" in joined
    has_group = "GROUP" in joined

    return has_card_text or has_rx or (has_member and has_group and has_copay)


def _layout_version(textract_or_parsed: Dict[str, Any], form_type: str) -> str:
    blocks = (
        textract_or_parsed.get("Blocks", [])
        if isinstance(textract_or_parsed, dict)
        else []
    )

    if not blocks and isinstance(textract_or_parsed, dict):
        line_count = len(_lines(textract_or_parsed))
        if line_count < 5:
            return "low_resolution_or_sparse"
        return "text_only"

    line_count = len([
        block for block in blocks
        if block.get("BlockType") == "LINE"
    ])

    word_count = len([
        block for block in blocks
        if block.get("BlockType") == "WORD"
    ])

    if form_type == "CMS1500" and line_count > 35:
        return "scanned_variant"

    if form_type == "UB04" and line_count > 45:
        return "institutional_scanned_variant"

    if word_count < 60:
        return "low_resolution_or_sparse"

    return "adaptive"


def _score_to_confidence(score: int) -> float:
    if score <= 0:
        return 0.35

    if score >= 80:
        return 0.98

    return max(0.35, min(0.98, score / 100))
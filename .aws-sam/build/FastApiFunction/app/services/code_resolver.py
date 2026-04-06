# ehr_pipeline/app/services/code_resolver.py
from typing import List, Dict, Any, Optional, Tuple
import re
from .catalogs import get_icd, get_cpt, load_icd_catalog, load_cpt_catalog
from .ehr_extractor import extract_icd_and_cpt
from .matcher import match_by_description

# add more EHR text fields as needed:
NOTE_COLS = [
  "diagnosis", "diagnoses", "chief_complaint", "chief complaint",
  "assessment", "impression", "notes", "plan",
  "subjective", "objective", "hpi", "ros", "exam",
  "provider_notes", "doctor_notes"
]

ICD_COLS = ["icd", "icd_code", "icd10", "icd-10", "icd-10 code", "dx", "diagnosis_code"]
CPT_COLS = ["cpt", "cpt_code", "procedure_code", "hcpcs", "code"]

def _lower_map(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).strip().lower(): v for k, v in row.items()}

def _first_present_value(lrow: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    for c in candidates:
        key = c.strip().lower()
        if key in lrow:
            v = str(lrow[key]).strip()
            if v:
                return v
    return None

def _collect_text(lrow: Dict[str, Any]) -> str:
    parts: List[str] = []
    for n in NOTE_COLS:
        if n in lrow:
            parts.append(str(lrow[n] or ""))
    return " ".join(parts)

def resolve_codes_for_row(row: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns two lists of dicts:
      ICDs: [{code, description, score, source}]
      CPTs: [{code, description, fee, score, source}]
    Strategy:
      1) If codes present in row, enrich and keep (source='code').
      2) Else infer via keywords (extract_ehr_data) → codes (source='keyword').
      3) Also try description search against master CSVs (source='desc_*').
      Pick the best (highest score / priority: code > desc_exact > desc_fuzzy > keyword).
    """
    lrow = _lower_map(row)
    icd_index = load_icd_catalog()
    cpt_index = load_cpt_catalog()

    out_icds: List[Dict[str, Any]] = []
    out_cpts: List[Dict[str, Any]] = []

    # 1) Codes present?
    raw_icd_codes = _first_present_value(lrow, ICD_COLS)
    raw_cpt_codes = _first_present_value(lrow, CPT_COLS)

    def _split_codes(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        return [re.sub(r"\s+", "", c).upper() for c in raw.split(",") if c.strip()]

    # Enrich direct codes
    for code in _split_codes(raw_icd_codes):
        hit = get_icd(code) or {"code": code, "description": ""}
        out_icds.append({"code": hit["code"], "description": hit.get("description", ""), "score": 100.0, "source": "code"})

    for code in _split_codes(raw_cpt_codes):
        hit = get_cpt(code) or {"code": code, "description": "", "fee": 0.0}
        out_cpts.append({"code": hit["code"], "description": hit.get("description", ""), "fee": float(hit.get("fee", 0.0) or 0.0), "score": 100.0, "source": "code"})

    # 2) If still missing, infer by keywords
    if not out_icds or not out_cpts:
        texts = _collect_text(lrow)
        kw_icds, kw_cpts = extract_icd_and_cpt([texts])
        for code in kw_icds:
            hit = get_icd(code) or {"code": code, "description": ""}
            out_icds.append({"code": hit["code"], "description": hit.get("description", ""), "score": 70.0, "source": "keyword"})
        for code in kw_cpts:
            hit = get_cpt(code) or {"code": code, "description": "", "fee": 0.0}
            out_cpts.append({"code": hit["code"], "description": hit.get("description", ""), "fee": float(hit.get("fee", 0.0) or 0.0), "score": 70.0, "source": "keyword"})

    # 3) Also try description search on the same text (can override keywords if better)
    texts = _collect_text(lrow)
    icd_desc_hit = match_by_description(texts, icd_index, min_score=85)
    if icd_desc_hit:
        code, desc, sc, src = icd_desc_hit
        out_icds.append({"code": code, "description": desc, "score": sc, "source": src})

    cpt_desc_hit = match_by_description(texts, cpt_index, min_score=85)
    if cpt_desc_hit:
        code, desc, sc, src = cpt_desc_hit
        fee = float((cpt_index.get(code) or {}).get("fee", 0.0) or 0.0)
        out_cpts.append({"code": code, "description": desc, "fee": fee, "score": sc, "source": src})

    # Deduplicate by code keeping the best source/score
    def _dedup(items: List[Dict[str, Any]], is_cpt: bool) -> List[Dict[str, Any]]:
        best: Dict[str, Dict[str, Any]] = {}
        for it in items:
            code = it["code"]
            prev = best.get(code)
            if not prev or (it.get("score", 0) > prev.get("score", 0)):
                best[code] = it
        # stable order: prefer code > desc_exact > desc_fuzzy > keyword
        priority = {"code": 4, "desc_exact": 3, "desc_fuzzy": 2, "desc_contains": 2, "keyword": 1}
        ret = sorted(best.values(), key=lambda d: (priority.get(d.get("source",""), 0), d.get("score", 0)), reverse=True)
        return ret

    out_icds = _dedup(out_icds, is_cpt=False)
    out_cpts = _dedup(out_cpts, is_cpt=True)

    return out_icds, out_cpts

def decide_e_claim(row: Dict[str, Any], icds: List[Dict[str, Any]], cpts: List[Dict[str, Any]]) -> str:
    text = " ".join(str(v) for v in row.values()).lower()
    facility_words = ["inpatient", "admit", "admission", "discharge", "ward", "ip", "er visit", "emergency", "icu", "theatre", "ot"]
    return "UB-04" if any(w in text for w in facility_words) else "CMS-1500"

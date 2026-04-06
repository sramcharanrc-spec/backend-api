# ehr_pipeline/app/services/ehr_extractor.py
from typing import List, Tuple
from ..icd.icd_dict import ICD_KEYWORDS, CPT_KEYWORDS

def _lower_concat(*parts: str) -> str:
    return " ".join([p for p in parts if p]).lower()

def extract_icd_and_cpt(texts: List[str]) -> Tuple[List[str], List[str]]:
    """
    Returns:
      icd_codes: list[str]  (e.g., ['R50.9'])
      cpt_codes: list[str]  (e.g., ['99213','87804'])
    """
    blob = _lower_concat(*texts)

    icd_codes = set()
    for k, code in ICD_KEYWORDS.items():
        if k in blob:
            icd_codes.add(code.upper().replace(" ", ""))

    cpt_codes = []
    for k, tup in CPT_KEYWORDS.items():
        if k in blob:
            cpt = tup[0]
            cpt_codes.append(cpt.upper().replace(" ", ""))

    return sorted(icd_codes), list(dict.fromkeys(cpt_codes))  # uniq, preserve order

# ehr_pipeline/app/services/matcher.py
from typing import List, Dict, Any, Optional, Tuple
import re

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def _mk_catalog_lists(idx: Dict[str, Dict[str, Any]]) -> Tuple[List[str], Dict[str, str]]:
    """
    Returns:
      titles: list of normalized descriptions
      map_desc_to_code: normalized description -> code
    """
    titles, mapping = [], {}
    for code, row in idx.items():
        desc = _norm(row.get("description", ""))
        if not desc:
            continue
        titles.append(desc)
        mapping[desc] = code
    return titles, mapping

def match_by_description(
    text: str,
    index: Dict[str, Dict[str, Any]],
    min_score: int = 85
) -> Optional[Tuple[str, str, float, str]]:
    """
    Try to match free text against a catalog's descriptions.
    Returns (code, description, score, source) or None.
    source ∈ {"desc_exact","desc_fuzzy"}.
    """
    text_n = _norm(text)
    if not text_n:
        return None

    titles, map_desc_to_code = _mk_catalog_lists(index)

    # exact (fast)
    if text_n in map_desc_to_code:
        code = map_desc_to_code[text_n]
        desc = index[code].get("description", "")
        return code, desc, 100.0, "desc_exact"

    # fuzzy
    if not titles:
        return None

    if HAS_RAPIDFUZZ:
        best = process.extractOne(text_n, titles, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= min_score:
            desc_norm = best[0]
            code = map_desc_to_code[desc_norm]
            return code, index[code].get("description", ""), float(best[1]), "desc_fuzzy"
    else:
        # fallback: simple contains
        for t in titles:
            if t in text_n or text_n in t:
                code = map_desc_to_code[t]
                return code, index[code].get("description", ""), 80.0, "desc_contains"
    return None

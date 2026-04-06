# ehr_pipeline/app/services/catalogs.py
import os
import pandas as pd
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

ICD_PATH = os.path.join(DATA_DIR, "icd10_master.csv")
CPT_PATH = os.path.join(DATA_DIR, "2025_DHS_code_list.csv")

_icd_index: Dict[str, Dict[str, Any]] | None = None
_cpt_index: Dict[str, Dict[str, Any]] | None = None

def _norm_cols(df: pd.DataFrame):
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def _to_str(x) -> str:
    return str(x).strip()

def load_icd_catalog(force: bool=False):
    global _icd_index
    if _icd_index is not None and not force:
        return _icd_index
    if not os.path.exists(ICD_PATH):
        _icd_index = {}
        return _icd_index

    df = pd.read_csv(ICD_PATH, dtype=str, keep_default_na=False)
    df = _norm_cols(df)

    # common header variants
    code_col = next((c for c in df.columns if c in ["code","icd","icd_code","icd10","icd-10 code","icd-10"]), None)
    desc_col = next((c for c in df.columns if c in ["description","desc","title","long description","short description"]), None)
    if not code_col:
        raise ValueError("icd10_master.csv is missing a 'code' column (variants: code, icd_code, icd10).")
    if not desc_col:
        raise ValueError("icd10_master.csv is missing a description column (e.g., description/title).")

    idx: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        code = _to_str(r[code_col]).upper().replace(" ", "")
        if not code:
            continue
        idx[code] = {
            "code": code,
            "description": _to_str(r[desc_col]),
        }
    _icd_index = idx
    return _icd_index

def load_cpt_catalog(force: bool=False):
    global _cpt_index
    if _cpt_index is not None and not force:
        return _cpt_index
    if not os.path.exists(CPT_PATH):
        _cpt_index = {}
        return _cpt_index

    df = pd.read_csv(CPT_PATH, dtype=str, keep_default_na=False)
    df = _norm_cols(df)

    # common header variants
    code_col = next((c for c in df.columns if c in ["cpt","code","cpt_code"]), None)
    desc_col = next((c for c in df.columns if c in ["description","desc","service description","long description","short description"]), None)
    fee_col  = next((c for c in df.columns if c in ["fee","price","amount","charge","rate"]), None)

    if not code_col:
        raise ValueError("2025_DHS_code_list.csv is missing a CPT code column (e.g., cpt/code).")
    if not desc_col:
        raise ValueError("2025_DHS_code_list.csv is missing a description column.")
    # fee optional; default 0.0

    idx: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        code = _to_str(r[code_col]).upper().replace(" ", "")
        if not code:
            continue
        desc = _to_str(r[desc_col])
        fee  = 0.0
        if fee_col:
            raw = _to_str(r[fee_col]).replace(",", "")
            try:
                fee = float(raw)
            except:
                fee = 0.0
        idx[code] = {
            "code": code,
            "description": desc,
            "fee": fee,
        }
    _cpt_index = idx
    return _cpt_index

def get_icd(code: str) -> Optional[Dict[str, Any]]:
    if code is None:
        return None
    code = code.strip().upper().replace(" ", "")
    if not code:
        return None
    if _icd_index is None:
        load_icd_catalog()
    return _icd_index.get(code, None)

def get_cpt(code: str) -> Optional[Dict[str, Any]]:
    if code is None:
        return None
    code = code.strip().upper().replace(" ", "")
    if not code:
        return None
    if _cpt_index is None:
        load_cpt_catalog()
    return _cpt_index.get(code, None)

def reload_catalogs():
    load_icd_catalog(force=True)
    load_cpt_catalog(force=True)

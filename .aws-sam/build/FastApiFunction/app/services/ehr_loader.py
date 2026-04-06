# ehr_pipeline/services/ehr_loader.py
from __future__ import annotations

import io, re
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd

from ..models.ehr_record import EHRRecord
# from .s3_client import load_ehr_as_rows

# ---------- S3 entry point ----------

def load_from_s3(key: str):
    """
    Loads raw rows from S3 and returns normalized records ready for the UI.
    """
    rows = load_ehr_as_rows(key)
    normalized = normalize_records(rows)
    return normalized


# ---------- Normalization Helpers ----------

_CANONICAL_MAP = {
    "patient_id": ["patient_id", "id", "record_id", "mrn", "patientid", "patient id", "encounter_id", "uid"],
    "patient_name": ["patient_name", "name", "full_name", "patient", "patient name"],
    "age": ["age", "patient_age", "age_years", "years"],
    "diagnosis": ["diagnosis", "dx", "assessment", "problem", "chief_complaint", "impression"],
    "visit_date": ["visit_date", "date", "encounter_date", "admission_date", "visit", "visit date"]
}

_DATE_PATTERNS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%Y/%m/%d", "%d %b %Y", "%b %d, %Y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"
]

_int_re = re.compile(r"^\s*-?\d+\s*$")

def _try_parse_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if _int_re.match(s):
        try:
            return int(s)
        except Exception:
            return None
    try:
        f = float(s.replace(",", ""))
        return int(f)
    except Exception:
        return None

def _try_parse_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt.date().isoformat()
    except Exception:
        pass
    for fmt in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    if s.isdigit():
        try:
            ts = int(s)
            if ts > 1_000_000_000_000:
                ts = ts // 1000
            dt = datetime.utcfromtimestamp(ts)
            return dt.date().isoformat()
        except Exception:
            pass
    return s

def normalize_records(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize arbitrary EHR rows into a stable structure for frontend display.
    """
    out = []
    if not rows:
        return out

    # map lowercase -> actual column name
    all_keys = {}
    for r in rows:
        for k in r.keys():
            if k:
                all_keys[str(k).strip().lower()] = k

    def find_col(candidates):
        for c in candidates:
            if c in all_keys:
                return all_keys[c]
        return None

    pid_col = find_col(_CANONICAL_MAP["patient_id"])
    pname_col = find_col(_CANONICAL_MAP["patient_name"])
    age_col = find_col(_CANONICAL_MAP["age"])
    diag_col = find_col(_CANONICAL_MAP["diagnosis"])
    visit_col = find_col(_CANONICAL_MAP["visit_date"])

    for r in rows:
        raw = dict(r)
        val = lambda c: raw.get(c, "") if c else ""

        patient_id = val(pid_col) or val(pname_col) or raw.get("id") or ""
        patient_name = val(pname_col) or val(pid_col) or ""
        age = _try_parse_int(val(age_col))
        diagnosis = val(diag_col) or raw.get("diagnosis") or ""
        visit_date = _try_parse_date(val(visit_col) or raw.get("date") or "")

        out.append({
            "patient_id": str(patient_id).strip(),
            "patient_name": str(patient_name).strip(),
            "age": age,
            "diagnosis": str(diagnosis).strip(),
            "visit_date": visit_date,
            "raw": raw,
        })
    return out


# ---------- Parsing helpers (CSV/Excel -> EHRRecord) ----------

ID_SYNONYMS = [
    "id", "record_id", "encounter_id", "visit_id",
    "patient_visit_id", "mrn", "uid", "patient_key"
]

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _find_id_column(cols: List[str]) -> Optional[str]:
    lower_map = {c.strip().lower(): c for c in cols}
    for name in ID_SYNONYMS:
        if name in lower_map:
            return lower_map[name]
    return None

def _decode_best(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8-sig")
    except Exception:
        return raw_bytes.decode("utf-8", errors="replace")

def _read_dataframe(filename: Optional[str], raw: bytes) -> pd.DataFrame:
    """
    Robust reader for CSV/Excel files with cleaning.
    """
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        df = df.dropna(axis=1, how="all")
        df = df.dropna(axis=0, how="all")
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")
        return df

    # Excel
    if filename and filename.lower().endswith((".xlsx", ".xls")):
        try:
            sheets = pd.read_excel(io.BytesIO(raw), dtype=str, sheet_name=None, engine=None)
            for _, df in sheets.items():
                df = _clean(df)
                if not df.empty and df.shape[1] > 0:
                    return df.fillna("")
            return pd.DataFrame()
        except Exception:
            pass

    # CSV
    text = _decode_best(raw)
    for sep in [None, "\t", ","]:
        try:
            df = pd.read_csv(
                io.StringIO(text),
                dtype=str,
                keep_default_na=False,
                sep=sep,
                engine="python",
                skip_blank_lines=True,
            )
            df = _clean(df)
            if not df.empty:
                return df.fillna("")
        except Exception:
            continue

    # Headerless CSV
    try:
        tmp = pd.read_csv(
            io.StringIO(text),
            dtype=str,
            keep_default_na=False,
            header=None,
            skip_blank_lines=True,
        )
        tmp = _clean(tmp)
        if not tmp.empty:
            header_idx = tmp.index[0]
            tmp.columns = [str(c).strip() for c in tmp.iloc[header_idx].tolist()]
            tmp = tmp.iloc[header_idx + 1 :]
            tmp = _clean(tmp)
            return tmp.fillna("")
    except Exception:
        pass

    return pd.DataFrame()

def load_csv_to_records(raw_bytes: bytes, note_fields: List[str], filename: Optional[str] = None) -> list[EHRRecord]:
    df = _read_dataframe(filename, raw_bytes)
    if df.empty:
        return []

    df = _norm_cols(df)
    df = df.replace(r"^\s*$", "", regex=True)

    id_col = _find_id_column(list(df.columns))
    if not id_col:
        gen_col = "__gen_id"
        df[gen_col] = [str(i) for i in range(1, len(df) + 1)]
        id_col = gen_col

    lower_to_actual = {c.strip().lower(): c for c in df.columns}

    records: list[EHRRecord] = []
    for _, row in df.iterrows():
        raw = row.to_dict()

        def get_lower(name: str) -> str:
            col = lower_to_actual.get(name, None)
            return str(raw.get(col, "")).strip() if col else ""

        rec = EHRRecord(
            id=str(raw.get(id_col, "")).strip(),
            patient_id=(get_lower("patient_id") or None),
            chief_complaint=(get_lower("chief_complaint") or None),
            assessment=(get_lower("assessment") or None),
            notes=(get_lower("notes") or None),
            raw=raw,
        )
        records.append(rec)
    return records

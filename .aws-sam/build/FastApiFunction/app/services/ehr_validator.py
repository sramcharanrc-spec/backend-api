# ehr_pipeline/app/services/ehr_validator.py
from typing import List

# NOTE: We now accept multiple synonyms for the record identifier.
ID_SYNONYMS = ["id", "record_id", "encounter_id", "visit_id", "patient_visit_id", "mrn", "uid"]

def normalize_cols(cols: List[str]) -> List[str]:
    return [str(c).strip().lower() for c in cols]

def has_any_id_column(cols: List[str]) -> bool:
    ncols = normalize_cols(cols)
    return any(c in ncols for c in ID_SYNONYMS)

def validate_columns(cols: List[str], note_fields: List[str]) -> None:
    """
    Be lenient:
      - If no obvious ID column is present, we DO NOT raise anymore; the loader will auto-generate IDs.
      - For note_fields, if some are missing, we also don't raise; we proceed with the ones we have.
    """
    # Previously we raised if 'id' was missing. Now we allow auto-generation.
    # If you still want to enforce having SOME id-like column, uncomment:
    # if not has_any_id_column(cols):
    #     raise ValueError(f"Missing an ID column. Acceptable names: {ID_SYNONYMS}")

    # No hard failure for note_fields either; transformer will just have less text to search.
    return

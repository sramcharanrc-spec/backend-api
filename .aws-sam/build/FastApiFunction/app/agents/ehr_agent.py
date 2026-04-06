from app.services.ehr_extractor import extract_ehr_data
from app.services.ehr_validator import validate_ehr_data
from app.services.ehr_transformer import transform_ehr_data

def run_ehr_pipeline(file_path: str):
    # Step 1: Extract
    df = extract_ehr_data(file_path)

    # Step 2: Validate
    valid, msg = validate_ehr_data(df)
    if not valid:
        raise ValueError(msg)

    # Step 3: Transform
    df_transformed = transform_ehr_data(df)

    return df_transformed.to_dict(orient="records")

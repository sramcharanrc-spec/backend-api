import os


OLD_BUCKET_NAME = "ehr-claims-bucket-agenticai"
BUCKET_NAME = os.getenv("S3_BUCKET", OLD_BUCKET_NAME)
EDI_OUTPUT_BUCKET = os.getenv("EDI_OUTPUT_BUCKET", os.getenv("OUTPUT_BUCKET", ""))
FORM_OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "")

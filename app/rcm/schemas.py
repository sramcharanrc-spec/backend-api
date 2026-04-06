from pydantic import BaseModel

class SubmitClaimRequest(BaseModel):
    patient_id: str

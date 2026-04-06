import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from ehr_pipeline.services.s3_client import list_objects, get_presigned_url, load_ehr_as_rows




app = FastAPI(title="AgenticAI EHR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/ehr/list")
def api_list(prefix: str | None = Query(None)):
    return {"items": list_objects(prefix)}

@app.get("/api/ehr/url")
def api_url(key: str = Query(...)):
    try:
        return {"url": get_presigned_url(key)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/ehr/json")
def api_json(key: str = Query(...)):
    try:
        rows = load_ehr_as_rows(key)
        return rows
    except Exception as e:
        raise HTTPException(500, str(e))
@app.get("/api/ehr/load")
def api_load(key: str = Query(..., description="S3 object key")):
  try:
      from ehr_pipeline.services.ehr_loader import load_from_s3
      return load_from_s3(key)
  except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
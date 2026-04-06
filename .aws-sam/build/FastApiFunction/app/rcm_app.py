# app/rcm_app.py
from fastapi import FastAPI
from app.rcm.router import router as rcm_router

app = FastAPI(title="RCM Backend (Sample Only)")
app.include_router(rcm_router)

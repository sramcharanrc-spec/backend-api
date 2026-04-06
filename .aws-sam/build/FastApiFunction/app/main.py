# ehr_pipeline/app/main.py
from pathlib import Path
import os
import inspect
import asyncio
import logging
from typing import List, Optional


from botocore.exceptions import BotoCoreError, ClientError
import boto3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ehr_pipeline")

# --- load .env from repo root (one level up from this file) ---
ROOT = Path(__file__).resolve().parents[1]
dotenv_path = ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f"Loaded .env from {dotenv_path}")

# --- attempt to import routers (they may not exist in all setups) ---
coder_router = None
claims_router = None
ehr_router = None
icd_router = None
rcm_router = None

try:
    from app.router_coder import router as coder_router  # type: ignore
    logger.info("Loaded router: router_coder")
except Exception:
    coder_router = None

try:
    from app.router_claims import router as claims_router  # type: ignore
    logger.info("Loaded router: router_claims")
except Exception:
    claims_router = None

try:
    from app.router_ehr import router as ehr_router  # type: ignore
    logger.info("Loaded router: router_ehr")
except Exception:
    ehr_router = None

try:
    from app.router_icd import router as icd_router  # type: ignore
    logger.info("Loaded router: router_icd")
except Exception:
    icd_router = None

# RCM router (may define its own prefix inside the router module)
try:
    from app.rcm.router import router as rcm_router  # type: ignore
    logger.info("Loaded router: app.rcm.router")
except Exception:
    rcm_router = None

# Optional DB init for rcm (if present)
init_db = None
try:
    from app.rcm.db import init_db as _init_db  # type: ignore
    init_db = _init_db
    logger.info("Loaded rcm.init_db")
except Exception:
    try:
        from app.rcm import db as rcm_db  # type: ignore
        init_db = getattr(rcm_db, "init_db", None)
        if init_db:
            logger.info("Loaded rcm.db.init_db")
    except Exception:
        init_db = None

# Create FastAPI app
app = FastAPI(title="AgenticAI-HC EHR Pipeline", version="0.2.0")

# ---- CORS configuration ----
dev_frontend = os.getenv("DEV_FRONTEND_ORIGIN", "http://localhost:5173")
allow_origins_env = os.getenv("ALLOW_ORIGINS")  # optional comma-separated list

if allow_origins_env:
    allow_origins: List[str] = [o.strip() for o in allow_origins_env.split(",") if o.strip()]
else:
    allow_origins = [dev_frontend, "http://localhost:3000", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Startup: init DB if available ----
@app.on_event("startup")
async def _startup():
    if init_db:
        try:
            if inspect.iscoroutinefunction(init_db):
                await init_db()
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, init_db)
            logger.info("[startup] rcm db initialized (init_db ran).")
        except Exception as e:
            logger.warning(f"[startup-warning] init_db raised an exception: {e}")

# --- Include routers (only those that successfully imported) ---
# Note: many routers may set their own prefix inside their module.
if coder_router is not None:
    app.include_router(coder_router)
    logger.info("Included coder_router")

if claims_router is not None:
    app.include_router(claims_router)
    logger.info("Included claims_router")

if ehr_router is not None:
    app.include_router(ehr_router)
    logger.info("Included ehr_router")

if icd_router is not None:
    app.include_router(icd_router)
    logger.info("Included icd_router")

if rcm_router is not None:
    app.include_router(rcm_router)
    logger.info("Included rcm_router")

# --- Health and root endpoints ---
@app.get("/", tags=["meta"])
def root():
    return {"msg": "AgenticAI-HC API running. See /health and /docs."}

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}

# Optional: debug middleware to log incoming requests (comment out if noisy)
# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     body = await request.body()
#     logger.debug(f"Incoming request: {request.method} {request.url.path} body={body[:100]}")
#     response = await call_next(request)
#     return response

@app.post("/agentRun", tags=["compat"])
async def agent_run_compat(request: Request):
    """
    Calls AWS Bedrock Agent Runtime and returns the actual rawResponse to frontend.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Accept both agentName or agentId
    agent_id = body.get("agentId") or body.get("agentName") or body.get("agent") or "ETL Agent"
    input_text = body.get("inputText") or body.get("input") or body.get("text") or ""

    # --- AGENT MAP: add all your agents here ---
    AGENT_MAP = {
        "etl agent": {"agentId": "N69PXCPOI9", "agentAliasId": "5Z4IYRRA2E"},
        "summarizer agent": {"agentId": "REPLACE_SUMMARY_ID", "agentAliasId": "REPLACE_SUMMARY_ALIAS"},
        "claim agent": {"agentId": "REPLACE_CLAIM_ID", "agentAliasId": "REPLACE_CLAIM_ALIAS"},
        "analytics agent": {"agentId": "REPLACE_ANALYTICS_ID", "agentAliasId": "REPLACE_ANALYTICS_ALIAS"},
        "payment agent": {"agentId": "REPLACE_PAYMENT_ID", "agentAliasId": "REPLACE_PAYMENT_ALIAS"},
    }

    # normalize lookup
    lookup = (agent_id or "").strip().lower()
    agent_entry = AGENT_MAP.get(lookup)
    if not agent_entry:
        # helpful response for UI
        return JSONResponse(content={"ok": False, "error": f"Unknown agent '{agent_id}'"}, status_code=200)

    # call bedrock
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")

    try:
        response = client.invoke_agent(
            agentId=agent_entry["agentId"],
            agentAliasId=agent_entry["agentAliasId"],
            sessionId="local-session",
            inputText=input_text,
        )

        # collect chunks robustly
        chunks = []
        for event in response.get("completion", []):
            # event structure may vary; handle common variants
            if isinstance(event, dict):
                if "chunk" in event and isinstance(event["chunk"], dict):
                    # bytes key or text key
                    if "bytes" in event["chunk"]:
                        b = event["chunk"].get("bytes") or b""
                        if isinstance(b, (bytes, bytearray)):
                            txt = b.decode("utf-8", errors="ignore")
                        else:
                            txt = str(b)
                        chunks.append(txt)
                    elif "text" in event["chunk"]:
                        chunks.append(event["chunk"].get("text", ""))
                elif "text" in event:
                    chunks.append(event.get("text", ""))

        combined = "".join(chunks)

        return JSONResponse(content={"ok": True, "agentId": agent_id, "rawResponse": combined}, status_code=200)

    except (BotoCoreError, ClientError) as e:
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from dotenv import load_dotenv

# load_dotenv()

# from app.rcm.rcm_router import router as rcm_router
# from app.lambdas.Shared.store import init_db
# from app.routes.intake_routes import router as intake_router
# from app.websocket.ws_router import router as ws_router
# from app.routes.analytics_router import router as analytics_router
# from app.routes.records_routes import router as records_router
# from app.routes.review_routes import router as review_router
# from app.routes.case_router import router as case_router
# # from app.routes.case_router import router as case_router
# # Create FastAPI app
# app = FastAPI(title="AgenticAI RCM")

# # Register routers
# app.include_router(intake_router, prefix="/intake")
# app.include_router(ws_router)
# app.include_router(rcm_router)
# app.include_router(analytics_router)
# app.include_router(records_router)
# app.include_router(review_router)
# # app.include_router(case_router, prefix='/api')
# app.include_router(case_router, prefix="/api")
# # CORS middleware (IMPORTANT for React/Vite)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:5173",
#         "http://localhost:5174",
#         "http://127.0.0.1:5173",
#         "http://127.0.0.1:5174",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Initialize database
# init_db()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# Routers
# -------------------------
from app.rcm.rcm_router import router as rcm_router
from app.routes.intake_routes import router as intake_router
from app.websocket.ws_router import router as ws_router
from app.routes.analytics_router import router as analytics_router
from app.routes.records_routes import router as records_router
from app.routes.review_routes import router as review_router
from app.routes.case_router import router as case_router
from app.websocket.ws_router import router as ws_router
from app.lambdas.Shared.store import init_db


# -------------------------
# App
# -------------------------
app = FastAPI(title="AgenticAI RCM")


# -------------------------
# CORS (FIXED 🔥)
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # 🔥 TEMP fix (avoid CORS errors completely)
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Root (DEBUG)
# -------------------------
@app.get("/")
def root():
    return {"status": "RCM Backend Running 🚀"}


# -------------------------
# Startup Event (FIXED 🔥)
# -------------------------
@app.on_event("startup")
def startup():
    print("🚀 Starting RCM Backend...")
    init_db()


# -------------------------
# Routers (ORDER MATTERS)
# -------------------------
app.include_router(ws_router)                 # 🔥 websocket first
app.include_router(intake_router, prefix="/intake")
app.include_router(rcm_router, prefix="/api/rcm")
app.include_router(analytics_router)
app.include_router(records_router)
app.include_router(review_router)
app.include_router(case_router, prefix="/api")

for route in app.routes:
    print(route.path)

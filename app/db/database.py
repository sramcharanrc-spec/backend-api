import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base

# Load .env explicitly
load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL missing from environment"
    )

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=30,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "sslmode": "require"
    },
    echo=False
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
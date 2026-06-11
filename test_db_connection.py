from app.db.database import engine

try:
    with engine.connect() as conn:
        print("✅ RDS CONNECTED SUCCESSFULLY")
except Exception as e:
    print("❌ CONNECTION FAILED:", str(e))
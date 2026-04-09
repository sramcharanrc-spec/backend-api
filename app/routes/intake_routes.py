from fastapi import APIRouter, UploadFile, File, HTTPException
from app.intake.s3_service import upload_file
from app.intake.processor import process_document
from app.utils.response_builder import build_clean_response

router = APIRouter()

BUCKET = "ehr-claims-bucket-agenticai"


# @router.post("/upload")
# async def upload(file: UploadFile = File(...)):

#     if not file:
#         raise HTTPException(status_code=400, detail="No file provided")

#     filename = f"uploads/{file.filename}"

#     print("📤 Uploading:", filename)

#     try:
#         # 1️⃣ Upload to S3
#         upload_file(file.file, filename)

#         print("✅ Uploaded to:", filename)

#         # 2️⃣ Process document
#         print("📄 Processing document:", BUCKET, filename)

#         result = await process_document(BUCKET, filename)

#         # 🔥 CLEAN RESPONSE HERE
#         # clean_response = build_clean_response(result)

#         return result

#     except Exception as e:
#         print("❌ Upload Error:", str(e))
#         raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload(file: UploadFile = File(...)):

    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename
    s3_key = f"uploads/{filename}"

    print("📤 Uploading:", s3_key)

    try:
        # 1️⃣ Upload to S3
        upload_file(file.file, s3_key)

        print("✅ Uploaded to:", s3_key)

        # 2️⃣ Process document
        print("📄 Processing document:", BUCKET, s3_key)

        result = await process_document(BUCKET, s3_key)

        return result

    except Exception as e:
        print("❌ Upload Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import APIRouter, Request
from app.orchestrator.pipeline_resumer import resume_pipeline

router = APIRouter()


@router.post("/webhook/salesforce")
async def handle_approval(request: Request):

    data = await request.json()

    case_id = data.get("case_id")
    claim_id = data.get("claim_id")

    if data.get("status") == "Approved":

        # 🔥 SEND REAL-TIME EVENT TO UI
        await manager.send_event(
            "salesforce",
            "approved",
            {
                "claim_id": claim_id
            }
        )

        # 🔄 Resume pipeline
        await resume_pipeline(case_id)

    return {"status": "received"}
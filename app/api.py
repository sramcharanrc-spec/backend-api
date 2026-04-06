from fastapi import FastAPI
from app.rcm.rcm_router import router
from app.lambdas.Shared.store import init_db

app = FastAPI(title="AgenticAI RCM Backend")

init_db()
app.include_router(router)


@router.post("/denial")
def receive_denial(payload: dict):
    from app.rcm.denial_835 import parse_835
    from app.rcm.submission import record_denial

    denial = parse_835(payload)
    return record_denial(
        denial["submission_id"],
        denial["denial_code"],
        denial["message"]
    )

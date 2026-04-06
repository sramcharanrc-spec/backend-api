from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    # 🔌 Connect client
    await manager.connect(websocket)

    # 🔥 Send initial connection message (VERY IMPORTANT)
    await websocket.send_json({
        "type": "connection",
        "message": "WebSocket connected successfully 🚀"
    })

    try:
        while True:
            # 🧠 Receive message (heartbeat / ping)
            data = await websocket.receive_text()

            # Optional: handle ping from frontend
            if data == "ping":
                await websocket.send_json({
                    "type": "pong"
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("❌ WebSocket disconnected")

    except Exception as e:
        print("⚠️ WebSocket error:", str(e))
        manager.disconnect(websocket)
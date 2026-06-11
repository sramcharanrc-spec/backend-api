import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.lambdas.analytics_agent.analytics import analytics_dashboard
from app.websocket.manager import manager


router = APIRouter()

HEARTBEAT_INTERVAL_SECONDS = 20


async def safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    """
    Safely send JSON to one websocket connection.
    If sending fails, disconnect the socket from manager.
    """
    try:
        await websocket.send_json(payload)
        return True

    except Exception as exc:
        print(f"WebSocket send failed: {exc}", flush=True)
        manager.disconnect(websocket)
        return False


async def heartbeat_loop(websocket: WebSocket, label: str = "WebSocket"):
    """
    Sends heartbeat messages until the websocket disconnects.
    """
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            await manager.heartbeat(websocket)

        except asyncio.CancelledError:
            break

        except Exception as exc:
            print(f"{label} heartbeat loop stopped: {exc}", flush=True)
            manager.disconnect(websocket)
            break


async def cleanup_connection(websocket: WebSocket, heartbeat_task: asyncio.Task):
    """
    Cleanly cancel heartbeat and disconnect websocket.
    """
    heartbeat_task.cancel()
    await asyncio.gather(heartbeat_task, return_exceptions=True)
    manager.disconnect(websocket)


@router.websocket("/ws/claims/{claim_id}")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main websocket endpoint used by frontend for pipeline, agent, claim,
    upload, validation, and payment events.
    """

    await manager.connect(websocket)

    await safe_send_json(websocket, {
        "type": "connection",
        "event": "connection",
        "status": "CONNECTED",
        "message": "WebSocket connected successfully",
        "timestamp": datetime.utcnow().isoformat(),
    })

    heartbeat_task = asyncio.create_task(
        heartbeat_loop(websocket, label="Main WebSocket")
    )

    try:
        while True:
            raw_message = await websocket.receive_text()

            # Simple ping/pong support.
            if raw_message == "ping":
                ok = await safe_send_json(websocket, {
                    "type": "pong",
                    "event": "pong",
                    "status": "CONNECTED",
                    "timestamp": datetime.utcnow().isoformat(),
                })

                if not ok:
                    break

                continue

            # Optional JSON message support.
            try:
                message = json.loads(raw_message)

            except json.JSONDecodeError:
                print(f"WebSocket message received: {raw_message}", flush=True)
                continue

            message_type = message.get("type") or message.get("event")

            if message_type == "ping":
                ok = await safe_send_json(websocket, {
                    "type": "pong",
                    "event": "pong",
                    "status": "CONNECTED",
                    "timestamp": datetime.utcnow().isoformat(),
                })

                if not ok:
                    break

            else:
                print(f"WebSocket JSON message received: {message}", flush=True)

    except WebSocketDisconnect:
        print("WebSocket disconnected", flush=True)

    except Exception as exc:
        print(f"WebSocket error: {exc}", flush=True)

    finally:
        await cleanup_connection(websocket, heartbeat_task)


@router.websocket("/ws/analytics")
async def analytics_websocket_endpoint(websocket: WebSocket):
    """
    Analytics websocket endpoint.

    Sends current analytics dashboard immediately, then keeps connection alive
    with heartbeat.
    """

    await manager.connect(websocket)

    try:
        dashboard = analytics_dashboard()

    except Exception as exc:
        dashboard = {
            "error": str(exc),
            "status": "FAILED",
        }

    await safe_send_json(websocket, {
        "type": "analytics_update",
        "event": "analytics_update",
        "status": "CONNECTED",
        "data": dashboard,
        "timestamp": datetime.utcnow().isoformat(),
    })

    heartbeat_task = asyncio.create_task(
        heartbeat_loop(websocket, label="Analytics WebSocket")
    )

    try:
        while True:
            raw_message = await websocket.receive_text()

            if raw_message == "ping":
                ok = await safe_send_json(websocket, {
                    "type": "pong",
                    "event": "pong",
                    "status": "CONNECTED",
                    "timestamp": datetime.utcnow().isoformat(),
                })

                if not ok:
                    break

            elif raw_message == "refresh_analytics":
                try:
                    dashboard = analytics_dashboard()

                except Exception as exc:
                    dashboard = {
                        "error": str(exc),
                        "status": "FAILED",
                    }

                await safe_send_json(websocket, {
                    "type": "analytics_update",
                    "event": "analytics_update",
                    "status": "UPDATED",
                    "data": dashboard,
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        print("Analytics WebSocket disconnected", flush=True)

    except Exception as exc:
        print(f"Analytics WebSocket error: {exc}", flush=True)

    finally:
        await cleanup_connection(websocket, heartbeat_task)
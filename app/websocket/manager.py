from fastapi import WebSocket
from typing import List
import json


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ WS Connected | Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"❌ WS Disconnected | Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                print("⚠️ WS Error:", str(e))
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    # 🔥 FIXED: NOW INSIDE CLASS
    async def send_event(self, step, status, data=None):

        if not self.active_connections:
            print("⚠️ No active WebSocket connections")
            return

        message = {
            "type": "agent_event",
            "step": step,
            "status": status,
            "data": data or {}
        }

        print("📡 Sending WS event:", message)

        for connection in self.active_connections:
            try:
                if connection.client_state.name != "CONNECTED":
                    continue

                await connection.send_json(message)

            except Exception as e:
                print("❌ WS Send Error:", e)

    async def send_pipeline_update(self, claim_id: str, stage: str, pipeline: dict):
        payload = {
            "event": "pipeline_update",
            "claim_id": claim_id,
            "stage": stage,
            "pipeline": pipeline
        }

        print(f"📊 PIPELINE UPDATE → {payload}")
        await self.broadcast(payload)


# Singleton
manager = ConnectionManager()
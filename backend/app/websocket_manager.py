"""
Channel-based WebSocket connection manager.

Channels:
  order:{order_id}      -> customer tracking a single order
  kitchen:{branch_id}   -> Kitchen Display System for a branch
  manager:{branch_id}   -> Manager Command Center for a branch

Every event published on the event bus is routed to the relevant channel(s) here.
Connections are isolated per branch/order so one restaurant never sees another's data.
"""
import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.channels: dict[str, set[WebSocket]] = {}

    async def connect(self, channel: str, ws: WebSocket):
        await ws.accept()
        self.channels.setdefault(channel, set()).add(ws)

    def disconnect(self, channel: str, ws: WebSocket):
        if channel in self.channels:
            self.channels[channel].discard(ws)
            if not self.channels[channel]:
                del self.channels[channel]

    async def send_to_channel(self, channel: str, message: dict):
        dead = []
        for ws in self.channels.get(channel, set()):
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)


manager = ConnectionManager()


async def route_event(event: dict):
    """Subscriber wired into the event bus. Fans a domain event out to the right WS channels."""
    payload = event["payload"]
    branch_id = event.get("branch_id")
    entity_type = event["entity_type"]

    if entity_type == "order":
        order_id = event["entity_id"]
        await manager.send_to_channel(f"order:{order_id}", event)

    if entity_type in ("order", "kitchen_task") and branch_id:
        await manager.send_to_channel(f"kitchen:{branch_id}", event)
        await manager.send_to_channel(f"manager:{branch_id}", event)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..websocket_manager import manager

router = APIRouter()


@router.websocket("/ws/order/{order_id}")
async def ws_order(websocket: WebSocket, order_id: str):
    channel = f"order:{order_id}"
    await manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()  # heartbeat / keep-alive pings from client
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


@router.websocket("/ws/kitchen/{branch_id}")
async def ws_kitchen(websocket: WebSocket, branch_id: str):
    channel = f"kitchen:{branch_id}"
    await manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


@router.websocket("/ws/manager/{branch_id}")
async def ws_manager(websocket: WebSocket, branch_id: str):
    channel = f"manager:{branch_id}"
    await manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)

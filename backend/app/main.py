from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .database import init_db
from .routers import orders, kitchen, ws, tables, menu, auth
from . import events
from .websocket_manager import route_event
from .seed import seed

app = FastAPI(title="ORBIT — Order Lifecycle & Kitchen Display System", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to real origins before production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router)
app.include_router(kitchen.router)
app.include_router(ws.router)
app.include_router(tables.router)
app.include_router(menu.router)
app.include_router(auth.router)

# Wire the WebSocket fan-out as a subscriber on the domain event bus.
events.subscribe(route_event)


@app.on_event("startup")
async def on_startup():
    await init_db()
    await seed()


from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse(url="/app/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the three frontend screens from the same origin as the API. This means a single
# public URL (e.g. from ngrok) works for everything — no separate static file server,
# no CORS complications, and the QR code + consumer app share one domain.
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

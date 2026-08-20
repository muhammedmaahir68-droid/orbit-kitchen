# ORBIT — Order Lifecycle + Kitchen Display System + Zero-Hardware-Cost QR Ordering

A real, working system. Not mocked, not random-number "real-time" — every state
change is a real row in a real database, and every WebSocket message is a real
domain event fired by a real state transition.

## The zero-cost hardware model

- **Table**: a printed QR sticker only (no tablet). The QR encodes a signed
  token — customers can't edit the URL to spoof another table.
- **Consumer**: their own phone browser (`frontend/consumer.html`).
- **Kitchen**: your iPad, browser open to `frontend/kitchen_display.html`, with sound.
- **Cashier/manager**: your laptop, browser open to `frontend/cashier_dashboard.html`.

All three are static HTML files talking to one backend over HTTP + WebSocket.
Nothing to install on any of the three screens beyond a browser.

## What's actually implemented

- **Order state machine** (`app/services/order_service.py`) — explicit allowed
  transitions, enforced server-side.
- **Signed table tokens** (`app/security.py`) — HMAC-signed, so a customer
  editing the QR's URL to change the table number is rejected server-side
  (tested: tampering returns HTTP 400).
- **Kitchen routing** — order items auto-assigned to their station on `QUEUED`.
- **Order status auto-driven by real kitchen task completion** — not a timer.
- **Real queue-based ETA** (`estimate_wait_seconds`) — sums actual backlog at
  each station the order touches, not a random guess.
- **Add items to an open order** — customer can order more mid-meal; it
  appends to the same order and routes fresh kitchen tasks immediately.
- **Event bus + EventLog** — durable, and the exact seam where Redis/Kafka
  slots in later with zero changes to any publisher or subscriber.
- **Sound alerts on the kitchen screen** — synthesized via Web Audio API
  (no external mp3 needed), fires on new orders and new items.
- **Cashier/manager live dashboard** — active orders, revenue, ready count,
  all from real WebSocket events plus a real "list active orders" backfill.

## Run it

```bash
cd backend
pip install -r requirements.txt --break-system-packages
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Seed IDs print on first boot. To swap SQLite for real Postgres 16:
```bash
export ORBIT_DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/orbit"
```

Set a real signing secret in production:
```bash
export ORBIT_SIGNING_SECRET="$(openssl rand -hex 32)"
```

### Serve the three screens

Any static file server works — e.g. from `frontend/`:
```bash
python3 -m http.server 8080
```
Then open, on each device, on the same WiFi as the laptop running the backend
(use the laptop's LAN IP, not `127.0.0.1`, from the phone/iPad):

- Kitchen iPad → `http://<laptop-ip>:8080/kitchen_display.html`
- Cashier laptop → `http://<laptop-ip>:8080/cashier_dashboard.html`
- Consumer phone → scans the printed QR (see below)

Update the `API`/`WS` base URL at the top of `consumer.html` (and enter it in
the config boxes of the other two) to `http://<laptop-ip>:8000`.

### Generate the table QR codes

```bash
cd backend
python3 generate_table_qrs.py --consumer-url "http://<laptop-ip>:8080/consumer.html"
```
This writes one PNG per seeded table to `backend/table_qr_codes/`. Print
these and stick one on each table.

### Verify the full flow yourself

```bash
cd backend
python3 test_flow.py
```

## API surface

```
GET    /api/v1/tables/resolve?token=...       resolve a QR token -> branch/table (rejects tampered tokens)
GET    /api/v1/tables/{id}/qr-token            admin: get/regenerate a table's token
GET    /api/v1/tables?branch_id=...            admin: list tables + tokens

GET    /api/v1/menu?branch_id=...              menu for the consumer app

POST   /api/v1/orders                          create order (table_token, items)
POST   /api/v1/orders/estimate                 real queue-based ETA before confirming
POST   /api/v1/orders/{id}/items                add items to an already-open order
GET    /api/v1/orders?branch_id=...            active orders (cashier dashboard)
GET    /api/v1/orders/{id}                     get order + items + tasks
PATCH  /api/v1/orders/{id}/status               transition order status

GET    /api/v1/kitchen/tasks?branch_id=...     active tasks for a branch (KDS feed)
PATCH  /api/v1/kitchen/tasks/{id}/status        advance a kitchen task

WS     /ws/order/{order_id}                    customer live tracking
WS     /ws/kitchen/{branch_id}                  KDS live feed
WS     /ws/manager/{branch_id}                  cashier/manager live feed

GET    /health
```

## Known simplifications (intentional for this stage)

- Payment is a mock — `consumer.html` auto-marks the order PAID with no real
  gateway. Swap that block for Razorpay/Stripe before this is real money.
- No staff auth/login yet on the kitchen or cashier screens — anyone on the
  WiFi with the URL can open them. Fine for a pilot on trusted WiFi, not for
  production.
- SQLite by default; swap to Postgres via `ORBIT_DATABASE_URL` before scaling
  past a single-device pilot (SQLite doesn't handle concurrent writers well).
- The event bus is in-process asyncio, not Redis — `app/events.py` is the
  documented seam to swap that in without touching any service code.

## Cost for this version

₹0 in new hardware if you already have a laptop, phone, and iPad — QR
stickers are the only physical thing to print (a few rupees each at any
print shop). Hosting is free for a pilot on your own laptop on local WiFi;
moving off-LAN later needs a small VPS (~₹500–1,500/month) plus a managed
Postgres tier (free tier is enough for a pilot, e.g. Neon).


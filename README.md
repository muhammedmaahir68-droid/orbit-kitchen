# ORBIT — One App, Three Roles, Real-Time, Installable

A single web app. Login (or scan a QR) routes you to your role's screen:
**Customer** (menu → cart → live tracking), **Kitchen** (KDS with sound), or
**Cashier** (live orders + revenue). Everything is one FastAPI backend + one
`frontend/index.html`, so it's one URL to deploy and one URL to open on every
device. It's also a PWA — "Add to Home Screen" installs it like a native app,
with the app shell cached for instant loads (live data always goes over the
network, deliberately never cached).

## How the single app routes by role

- **No query param, no saved session** → login screen (Customer tab / Staff Login tab)
- **URL has `?t=<qr_token>`** → customer view, table auto-detected, no login needed
- **Staff logs in** (`kitchen` / `cashier` demo accounts, seeded on first boot) →
  routed straight to the Kitchen Display or Cashier Dashboard, session persisted
  in `localStorage` so reloading the page keeps you logged in for ~12 hours

Demo logins (printed on server startup, **change before real use**):
```
kitchen / kitchen123
cashier / cashier123
```

## Run it locally

```bash
cd backend
pip install -r requirements.txt --break-system-packages
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open `http://localhost:8000/app/index.html` — that's the whole app, API and
frontend on the same origin, same port.

## Push to GitHub

```bash
cd orbit
git init                      # already done if you're using this zip as-is
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/orbit.git
git push -u origin main
```
(Create the empty repo on github.com first — no README/license, so there's no
merge conflict on first push.)

## Deploy for real (public URL, not a tunnel)

**Render.com (free tier, easiest for FastAPI):**
1. render.com → New → Web Service → connect your GitHub repo
2. Root directory: `backend`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add a free Render Postgres instance, copy its connection string, set it as
   an environment variable `ORBIT_DATABASE_URL` (format:
   `postgresql+asyncpg://...`, note the `+asyncpg` — Render gives you a plain
   `postgresql://` URL, add `+asyncpg` after `postgresql`)
6. Also set `ORBIT_SIGNING_SECRET` to a random value (`openssl rand -hex 32`)
7. Deploy. Render gives you a permanent URL like `https://orbit-xxxx.onrender.com`

That URL is now your one link for everything:
- Consumer QR → `https://orbit-xxxx.onrender.com/app/index.html?t=<token>`
- Staff → `https://orbit-xxxx.onrender.com/app/index.html`, log in

Regenerate QR codes with the real deployed URL:
```bash
cd backend
python3 generate_table_qrs.py --consumer-url "https://orbit-xxxx.onrender.com/app/index.html"
```

Free-tier Render web services sleep after inactivity and take ~30s to wake on
the first request — fine for a demo, worth upgrading to a paid tier before
real service.

## Install it as an app (PWA)

Once deployed (or even on localhost over HTTPS/tunnel):
- **Android/Chrome**: visit the URL → menu (⋮) → "Add to Home screen" / "Install app"
- **iPhone/iPad/Safari**: visit the URL → Share button → "Add to Home Screen"
- **Desktop Chrome/Edge**: address bar shows an install icon → click it

It then opens full-screen like a native app, with its own icon, no browser
chrome. Live data (orders, kitchen tasks) still requires network — this isn't
an offline-order-taking app, the service worker only caches the app shell for
fast loading.

## What's actually implemented

- **Order state machine**, server-enforced transitions, HTTP 409 on illegal ones
- **Signed table tokens** (`app/security.py`) — QR tampering is rejected (tested: HTTP 400)
- **Staff login** — PBKDF2 password hashing, signed session tokens with expiry
  (tested: wrong password → 401, valid session → 200, malformed token → 401)
- **Kitchen routing** — items auto-assigned to stations on `QUEUED`
- **Order status auto-driven by real kitchen task completion**, not a timer
- **Real queue-based ETA** — sums actual backlog per station, not a guess
- **Add items to an open order** — appends to the same order mid-meal, routes
  fresh kitchen tasks immediately
- **Event bus + EventLog** — durable, the seam where Redis/Kafka slots in later
- **Sound alerts on the kitchen screen** — synthesized via Web Audio API
- **Live cashier dashboard** — active orders, revenue, ready count, from real
  WebSocket events plus a real backfill on load
- **PWA** — installable, app-shell cached, live data never cached

## Verify the full flow yourself

```bash
cd backend
python3 test_flow.py
```

## API surface

```
POST   /api/v1/auth/login                     staff login -> session token
GET    /api/v1/auth/session?token=...          validate a session token

GET    /api/v1/tables/resolve?token=...        resolve a QR token (rejects tampered tokens)
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
GET    /app/*                                   the unified frontend (static)
```

## Known simplifications (intentional for this stage)

- Payment is a mock — auto-marks PAID with no real gateway. Swap that block
  in `index.html`'s `placeOrder()` for Razorpay/Stripe before real money moves.
- Staff session tokens gate the *frontend views* but the API endpoints
  themselves aren't yet locked behind auth middleware — anyone with the URL
  and a `branch_id` can call the kitchen/cashier endpoints directly. Fine for
  a pilot on a private link, add real endpoint-level auth before going public
  at scale.
- SQLite by default; switch to Postgres (`ORBIT_DATABASE_URL`) before any real
  deployment — Render's free-tier disk is ephemeral, so SQLite data won't
  survive a redeploy there.
- Event bus is in-process asyncio, not Redis — `app/events.py` is the
  documented seam to swap that in without touching service code.

## Cost

₹0 in new hardware — your own phone, laptop, and iPad are the three screens.
QR stickers cost a few rupees to print. Hosting is free to start (Render free
tier + Render free Postgres tier), a small monthly cost only once you outgrow
the free tier's sleep/idle behavior.



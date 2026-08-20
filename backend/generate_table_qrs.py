"""
Generates one QR code PNG per table. Each QR encodes a URL to the consumer web app
with that table's signed token as a query param — this is the entire "hardware"
requirement for the customer side: a printed sticker on the table.

Run this after the server has seeded its demo restaurant, or point it at your own
branch_id via the BRANCH_ID env var.

Usage:
    cd backend
    python3 generate_table_qrs.py --consumer-url http://<your-laptop-ip>:8080/consumer.html
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import qrcode
from sqlalchemy import select
from app.database import SessionLocal
from app.models import RestaurantTable
from app.security import make_table_token


async def main(consumer_url: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    async with SessionLocal() as db:
        result = await db.execute(select(RestaurantTable))
        tables = result.scalars().all()

    if not tables:
        print("No tables found. Start the server once first so it seeds demo data, or seed your own.")
        return

    for t in tables:
        token = make_table_token(t.branch_id, t.id)
        url = f"{consumer_url}?t={token}"
        img = qrcode.make(url)
        path = os.path.join(out_dir, f"table_{t.number}.png")
        img.save(path)
        print(f"Table {t.number}: {path}\n  -> {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer-url", required=True,
                         help="Public URL where consumer.html is hosted, e.g. http://192.168.1.5:8080/consumer.html")
    parser.add_argument("--out-dir", default="./table_qr_codes")
    args = parser.parse_args()
    asyncio.run(main(args.consumer_url, args.out_dir))

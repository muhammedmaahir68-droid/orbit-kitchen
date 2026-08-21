import os
import logging
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()

raw_url = os.getenv("ORBIT_DATABASE_URL") or os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./orbit.db"

# Clean up accidental whitespace, quotes, or prefixed key names (e.g. 'ORBIT_DATABASE_URL=postgresql://...')
raw_url = raw_url.strip().strip("'").strip('"')
if "=" in raw_url and not raw_url.startswith("sqlite") and not raw_url.startswith("postgres"):
    parts = raw_url.split("=", 1)
    if len(parts) == 2 and ("postgres" in parts[1] or "sqlite" in parts[1]):
        raw_url = parts[1].strip()

# Convert postgresql:// or postgres:// to postgresql+asyncpg://
if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Safely validate URL with SQLAlchemy make_url
try:
    if "..." in raw_url or "username:password" in raw_url:
        raise ValueError("Placeholder URL detected")
    make_url(raw_url)
    DATABASE_URL = raw_url
except Exception as err:
    logging.warning(f"Invalid DATABASE_URL ('{raw_url}'): {err}. Falling back to SQLite.")
    DATABASE_URL = "sqlite+aiosqlite:///./orbit.db"

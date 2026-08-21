import os
from dotenv import load_dotenv

load_dotenv()

# Read from ORBIT_DATABASE_URL or platform standard DATABASE_URL
raw_url = os.getenv("ORBIT_DATABASE_URL") or os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./orbit.db"

# Auto-convert standard Postgres URLs to SQLAlchemy asyncpg dialect
if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Fallback to SQLite if URL is a placeholder or invalid
if "..." in raw_url or "username:password" in raw_url:
    raw_url = "sqlite+aiosqlite:///./orbit.db"

DATABASE_URL = raw_url

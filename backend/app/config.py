import os
from dotenv import load_dotenv

load_dotenv()

# Swap DATABASE_URL to postgresql+asyncpg://user:pass@host/db for production Postgres 16.
# SQLite is used by default so the whole vertical slice runs with zero external services.
DATABASE_URL = os.getenv("ORBIT_DATABASE_URL", "sqlite+aiosqlite:///./orbit.db")

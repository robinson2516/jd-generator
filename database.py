"""Database connection and schema initialization."""
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        await _init_db(_pool)
    return _pool


async def _init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           SERIAL PRIMARY KEY,
                email        TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                plan         TEXT DEFAULT 'free'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_descriptions (
                id               SERIAL PRIMARY KEY,
                user_id          INTEGER REFERENCES users(id) ON DELETE CASCADE,
                company_name     TEXT,
                job_title        TEXT,
                skills           TEXT,
                experience_level TEXT,
                generated_text   TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            )
        """)

"""Database connection and schema initialization."""
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        url = os.environ["DATABASE_URL"]
        # Railway Postgres requires SSL
        _pool = await asyncpg.create_pool(url, ssl="require")
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
                company_website  TEXT,
                job_title        TEXT,
                skills           TEXT,
                experience_level TEXT,
                generated_text   TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE job_descriptions
            ADD COLUMN IF NOT EXISTS company_website TEXT
        """)

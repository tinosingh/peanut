"""Shared async Postgres connection pool."""
from __future__ import annotations

import os

from pgvector.psycopg import register_vector
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    """Return (creating if needed) the shared connection pool."""
    global _pool
    if _pool is None:
        db_url = os.environ["POSTGRES_URL"]
        # psycopg_pool uses standard postgresql:// DSN — strip SQLAlchemy +psycopg prefix if present
        if db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        _pool = AsyncConnectionPool(db_url, min_size=2, max_size=5, open=False)
        await _pool.open()
        async with _pool.connection() as conn:
            await register_vector(conn)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

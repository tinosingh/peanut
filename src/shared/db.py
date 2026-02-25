"""Shared async Postgres connection pool."""
from __future__ import annotations

import contextlib
import os

import structlog
from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()
_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    """Return (creating if needed) the shared connection pool.

    Pool is configured with:
    - max_lifetime: connections recycled after 1 hour
    - timeout: 30s for acquiring connections
    - statement_timeout: 30s for queries
    - idle_in_transaction_session_timeout: 60s
    """
    global _pool
    if _pool is None:
        db_url = os.environ["POSTGRES_URL"]
        # psycopg_pool uses standard postgresql:// DSN — strip SQLAlchemy +psycopg prefix if present
        if db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)

        try:
            _pool = AsyncConnectionPool(
                db_url,
                min_size=2,
                max_size=15,
                max_lifetime=3600,  # Recycle connections after 1 hour
                timeout=30.0,  # Connection acquisition timeout
                open=False,
                kwargs={
                    "options": "-c statement_timeout=30s -c idle_in_transaction_session_timeout=60s"
                }
            )
            await _pool.open()

            # Register pgvector extension (async version for async connections)
            async with _pool.connection() as conn:
                await register_vector_async(conn)

            logger.info("postgres_pool_initialized", min_size=2, max_size=15, max_lifetime=3600)
        except Exception as e:
            # Clean up partially initialized pool
            if _pool is not None:
                with contextlib.suppress(Exception):
                    await _pool.close()
                _pool = None
            logger.error("postgres_pool_init_failed", error=str(e))
            raise

    return _pool


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        try:
            logger.info("postgres_pool_closing")
            await _pool.close()
            logger.info("postgres_pool_closed")
        except Exception as e:
            logger.error("postgres_pool_close_failed", error=str(e))
        finally:
            _pool = None

"""Runtime config reader — reads from the config table in Postgres.

Application code calls get_config(pool) to get current values.
Falls back to env vars / defaults if DB is unavailable.
"""
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger()

_DEFAULTS: dict[str, Any] = {
    "bm25_weight": 0.5,
    "vector_weight": 0.5,
    "chunk_size": 512,
    "chunk_overlap": 50,
    "embed_model": os.getenv("EMBED_MODEL", "nomic-embed-text"),
    "rrf_k": 60,
    "embed_retry_max": 5,
    "search_cache_ttl": 60,
}


async def get_config(pool: Any) -> dict[str, Any]:
    """Read all config keys from the config table. Falls back to defaults."""
    try:
        async with pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT key, value, value_type FROM config"
            )).fetchall()
        config = dict(_DEFAULTS)
        for key, value, value_type in rows:
            if value_type == "int":
                config[key] = int(value)
            elif value_type == "float":
                config[key] = float(value)
            else:
                config[key] = value
        return config
    except Exception as exc:
        log.warning("config_read_failed", error=str(exc), using="defaults")
        return dict(_DEFAULTS)

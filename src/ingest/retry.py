"""Dead-letter retry with exponential backoff: 2s / 8s / 32s."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger()

RETRY_DELAYS = [2, 8, 32]   # seconds — matches PRD Story 1.10
MAX_RETRIES = len(RETRY_DELAYS)


async def retry_with_backoff(
    fn: Callable[[], Awaitable[Any]],
    *,
    label: str = "task",
) -> Any:
    """Call fn up to MAX_RETRIES times with exponential backoff.

    Raises the last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            log.warning("retry_attempt_failed",
                        label=label, attempt=attempt, max=MAX_RETRIES,
                        next_delay=delay if attempt < MAX_RETRIES else None,
                        error=str(exc))
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


async def retry_dead_letters(
    pool: Any,
    handle_file: Callable[[str, str], Awaitable[None]],
) -> int:
    """Re-process all rows in the dead_letter table.

    Returns count of successfully retried files.
    """
    import hashlib

    recovered = 0
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, file_path, attempts FROM dead_letter ORDER BY last_attempt"
        ).fetchall()

    for row_id, file_path, attempts in rows:
        if attempts > MAX_RETRIES:
            continue
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            sha = h.hexdigest()
            await handle_file(file_path, sha)
            async with pool.connection() as conn:
                await conn.execute("DELETE FROM dead_letter WHERE id = %s", (row_id,))
            recovered += 1
        except Exception as exc:
            async with pool.connection() as conn:
                await conn.execute("""
                    UPDATE dead_letter
                    SET attempts = attempts + 1, last_attempt = now(), error = %s
                    WHERE id = %s
                """, (str(exc), row_id))
    return recovered

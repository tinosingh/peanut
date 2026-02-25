"""Watchfiles-based drop-zone monitor with SHA-256 dedup and semaphore."""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog
from watchfiles import DefaultFilter, awatch

log = structlog.get_logger()

WATCHED_EXTENSIONS = {".mbox", ".mbx", ".pdf", ".md", ".markdown", ".eml"}
INGEST_SEMAPHORE = asyncio.Semaphore(10)


class ExtFilter(DefaultFilter):
    """Accept only files with recognised extensions."""

    def __call__(self, change: object, path: str) -> bool:
        return super().__call__(change, path) and any(
            path.endswith(ext) for ext in WATCHED_EXTENSIONS
        )


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def watch_drop_zone(
    drop_zone: str,
    handle_file: Callable[[str, str], Awaitable[None]],
) -> None:
    """Watch drop_zone and call handle_file(path, sha256) for each new file.

    Already-seen SHA-256 hashes are checked by the caller (DB dedup).
    """
    pause_sentinel = str(Path(drop_zone) / ".pause")
    log.info("watcher_started", drop_zone=drop_zone)
    async for changes in awatch(drop_zone, watch_filter=ExtFilter()):
        if Path(pause_sentinel).exists():
            log.info("watcher_paused", sentinel=pause_sentinel)
            continue
        for _change_type, path in changes:
            if path == pause_sentinel:
                continue  # skip the sentinel file itself
            async with INGEST_SEMAPHORE:
                try:
                    sha = sha256_file(path)
                    log.info("file_detected", path=path, sha256=sha[:8])
                    await handle_file(path, sha)
                except Exception as exc:
                    error_type = type(exc).__name__
                    log.error("file_handle_error", 
                        path=path, 
                        error=str(exc),
                        error_type=error_type)
                    # Soft errors (locks) are retried on next cycle
                    # Hard errors (permission) are skipped
                    if "Permission denied" in str(exc) or "Access denied" in str(exc):
                        log.warning("file_permission_denied", path=path)
                    # Else: retry on next watcher cycle

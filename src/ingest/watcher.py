"""Watchfiles-based drop-zone monitor with SHA-256 dedup and semaphore."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Callable, Awaitable

import structlog
from watchfiles import awatch, DefaultFilter

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
    log.info("watcher_started", drop_zone=drop_zone)
    async for changes in awatch(drop_zone, watch_filter=ExtFilter()):
        for _change_type, path in changes:
            async with INGEST_SEMAPHORE:
                try:
                    sha = sha256_file(path)
                    log.info("file_detected", path=path, sha256=sha[:8])
                    await handle_file(path, sha)
                except Exception as exc:
                    log.error("file_handle_error", path=path, error=str(exc))

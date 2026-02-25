"""API key auth middleware — scoped keys for read-only vs read-write access.

Keys are read from environment variables:
  API_KEY_READ   — accepted by all endpoints (GET + POST /search)
  API_KEY_WRITE  — accepted by all endpoints including mutation endpoints

No JWTs. Keys are passed via X-API-Key header.

If neither env var is set, auth is disabled (development mode).
Middleware logs all rejected requests at WARNING level.
"""
from __future__ import annotations

import os
import secrets

import structlog
from fastapi import HTTPException, Request

log = structlog.get_logger()

# Endpoints that require write-scoped key
_WRITE_PATHS = {"/ingest", "/entities/merge", "/entities/delete", "/config", "/pii/bulk-redact", "/pii/mark-public"}


def _get_keys() -> tuple[str | None, str | None]:
    read_key = os.getenv("API_KEY_READ")
    write_key = os.getenv("API_KEY_WRITE")
    return read_key, write_key


def check_api_key(request: Request) -> None:
    """Validate X-API-Key header. Raises HTTPException 401/403 on failure.

    No-op if neither API_KEY_READ nor API_KEY_WRITE is configured.
    """
    read_key, write_key = _get_keys()
    if not read_key and not write_key:
        return  # auth disabled in dev

    provided = request.headers.get("X-API-Key", "")
    if not provided:
        log.warning("auth_missing_key", path=str(request.url.path))
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    # Check if write scope needed
    needs_write = any(str(request.url.path).startswith(p) for p in _WRITE_PATHS)
    if needs_write and write_key:
        if not secrets.compare_digest(provided, write_key):
            log.warning("auth_invalid_write_key", path=str(request.url.path))
            raise HTTPException(status_code=403, detail="Invalid or insufficient API key")
    else:
        # Accept read or write key for read endpoints
        valid = (read_key and secrets.compare_digest(provided, read_key)) or \
                (write_key and secrets.compare_digest(provided, write_key))
        if not valid:
            log.warning("auth_invalid_read_key", path=str(request.url.path))
            raise HTTPException(status_code=403, detail="Invalid API key")


def generate_key(prefix: str = "pkg") -> str:
    """Generate a cryptographically secure API key."""
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{token}"

"""TUI controller entry point — FastAPI + Textual."""

import os
import signal
import sys

import structlog
import uvicorn
from fastapi import FastAPI

from src.api.config_api import router as config_router
from src.api.entities import router as entities_router
from src.api.graph_api import router as graph_router
from src.api.ingest_api import router as ingest_router
from src.api.metrics import router as metrics_router
from src.api.search import router as search_router

logger = structlog.get_logger()

app = FastAPI(title="pkg-tui", version="0.1.0")

# ── Rate limiting (slowapi) — graceful degradation if not installed ────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
except ImportError:
    pass  # slowapi not installed — rate limiting disabled

# ── CORS (localhost only, since this is a personal app) ──────────────────────
try:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["localhost", "127.0.0.1", "http://localhost:*"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )
except ImportError:
    pass  # starlette < 0.19, skip CORS

app.include_router(search_router)
app.include_router(entities_router)
app.include_router(config_router)
app.include_router(metrics_router)
app.include_router(ingest_router)
app.include_router(graph_router)


@app.middleware("http")
async def enforce_api_key(request, call_next):
    """Enforce API key auth on all paths except /health."""
    if request.url.path not in ("/health", "/metrics"):
        from fastapi.responses import JSONResponse

        from src.api.auth import check_api_key

        try:
            check_api_key(request)
        except Exception as exc:
            status = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "Unauthorized")
            return JSONResponse(status_code=status, content={"detail": detail})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    # CSP: only allow same-origin resources
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'unsafe-inline' unpkg.com; style-src 'unsafe-inline'"
    )
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Enable XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.get("/health")
async def health() -> dict:
    """Health check — verifies DB, FalkorDB, and Ollama connectivity.

    Returns 200 if all critical services (db, falkordb) are healthy.
    Returns 503 if any critical service is down.
    Ollama is non-critical (only affects embeddings, not reads).
    """
    import httpx

    from src.shared.db import get_pool

    checks: dict[str, str] = {}

    # Check PostgreSQL
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"

    # Check FalkorDB
    falkordb_host = os.getenv("FALKORDB_HOST", "pkg-graph")
    falkordb_port = int(os.getenv("FALKORDB_PORT", "6379"))
    try:
        import redis.asyncio as redis

        r = redis.Redis(
            host=falkordb_host, port=falkordb_port, socket_connect_timeout=2
        )
        await r.ping()
        await r.close()
        checks["falkordb"] = "ok"
    except ImportError:
        # Fallback if redis-py not installed - use raw socket
        try:
            import asyncio

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(falkordb_host, falkordb_port), timeout=2.0
            )
            writer.write(b"*1\r\n$4\r\nPING\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.read(100), timeout=1.0)
            writer.close()
            await writer.wait_closed()
            checks["falkordb"] = (
                "ok" if b"PONG" in response else "error: unexpected response"
            )
        except Exception as exc:
            checks["falkordb"] = f"error: {type(exc).__name__}"
    except Exception as exc:
        checks["falkordb"] = f"error: {type(exc).__name__}"

    # Check Ollama (non-critical)
    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            resp.raise_for_status()
        checks["ollama"] = "ok"
    except Exception as exc:
        checks["ollama"] = f"warning: {type(exc).__name__}"  # Non-critical

    # Critical services: postgres and falkordb
    critical_ok = checks.get("postgres") == "ok" and checks.get("falkordb") == "ok"
    all_ok = all(v == "ok" or v.startswith("warning:") for v in checks.values())

    status_code = 200 if critical_ok else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", **checks},
        status_code=status_code,
    )


@app.on_event("startup")
async def _mount_mcp() -> None:
    """Lazily mount MCP server at /mcp/ if SDK is available (T-034)."""
    from src.api.mcp_server import get_mcp_app

    mcp = get_mcp_app()
    if mcp is not None:
        app.mount("/mcp", mcp)


@app.on_event("shutdown")
async def _shutdown_pool() -> None:
    """Close the shared DB connection pool on graceful shutdown."""
    from src.shared.db import close_pool

    await close_pool()


def main() -> None:
    """Run the TUI controller with graceful shutdown handling."""
    shutdown_event = False

    def handle_shutdown(signum: int, frame) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        nonlocal shutdown_event
        if shutdown_event:
            logger.warning("force_shutdown", signal=signum)
            sys.exit(1)
        shutdown_event = True
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.info("shutdown_signal_received", signal=sig_name)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("tui_controller_starting", port=int(os.getenv("API_PORT", "8000")))

    try:
        uvicorn.run(
            "src.tui.main:app",
            host="0.0.0.0",
            port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
        )
    except KeyboardInterrupt:
        logger.info("tui_controller_interrupted")
    except Exception as e:
        logger.error("tui_controller_error", error=str(e))
        raise
    finally:
        logger.info("tui_controller_shutdown_complete")


if __name__ == "__main__":
    main()

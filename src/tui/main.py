"""TUI controller entry point — FastAPI + Textual."""
import os

import uvicorn
from fastapi import FastAPI

from src.api.config_api import router as config_router
from src.api.entities import router as entities_router
from src.api.metrics import router as metrics_router
from src.api.search import router as search_router

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

app.include_router(search_router)
app.include_router(entities_router)
app.include_router(config_router)
app.include_router(metrics_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
async def _mount_mcp() -> None:
    """Lazily mount MCP server at /mcp/ if SDK is available (T-034)."""
    from src.api.mcp_server import get_mcp_app
    mcp = get_mcp_app()
    if mcp is not None:
        app.mount("/mcp", mcp)


def main() -> None:
    uvicorn.run(
        "src.tui.main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()

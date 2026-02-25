"""TUI controller entry point — FastAPI + Textual."""
import os

import uvicorn
from fastapi import FastAPI

from src.api.search import router as search_router

app = FastAPI(title="pkg-tui", version="0.1.0")
app.include_router(search_router)


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

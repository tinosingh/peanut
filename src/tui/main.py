"""TUI controller entry point — FastAPI + Textual."""
import asyncio
import os

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="pkg-tui", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(
        "src.tui.main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()

"""Ingest worker entry point."""
import asyncio
import logging
import os

import structlog

log = structlog.get_logger()


async def main() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
        )
    )
    log.info("ingest_worker_starting")
    # Workers are registered in Epic 1 (T-011 onward)
    await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

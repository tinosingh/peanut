"""Embedding worker — asyncio Task inside ingest-worker.

Polls chunks WHERE embedding_status='pending', calls Ollama in batches,
writes embeddings back. Uses FOR UPDATE SKIP LOCKED for safe concurrent
operation if the container is accidentally double-launched.

After embed_retry_max failures (from config table, default 5),
sets embedding_status='failed' — prevents infinite retry loops.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

EMBED_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=500)
EMBED_POLL_INTERVAL = 1   # seconds between DB polls
EMBED_BATCH_SIZE = 200


async def call_ollama_embed(
    base_url: str, model: str, texts: list[str]
) -> list[list[float]]:
    """Call Ollama /api/embed and return a list of embedding vectors."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/api/embed",
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


async def embedding_worker(
    pool: Any,   # AsyncConnectionPool
    ollama_url: str,
    model: str,
    retry_max: int = 5,
) -> None:
    """Continuously poll for pending chunks and embed them."""
    log.info("embedding_worker_started", model=model)
    while True:
        try:
            async with pool.connection() as conn:
                # Atomic claim with FOR UPDATE SKIP LOCKED
                rows = await conn.execute("""
                    UPDATE chunks SET embedding_status = 'processing'
                    WHERE id IN (
                        SELECT id FROM chunks
                        WHERE embedding_status = 'pending'
                        ORDER BY id
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, text, retry_count
                """, (EMBED_BATCH_SIZE,)).fetchall()

            if not rows:
                await asyncio.sleep(EMBED_POLL_INTERVAL)
                continue

            ids = [str(r[0]) for r in rows]
            texts = [r[1] for r in rows]
            retry_counts = {str(r[0]): r[2] for r in rows}

            try:
                embeddings = await call_ollama_embed(ollama_url, model, texts)
                async with pool.connection() as conn:
                    for chunk_id, embedding in zip(ids, embeddings, strict=True):
                        await conn.execute("""
                            UPDATE chunks
                            SET embedding = %s,
                                embedded_at = now(),
                                embedding_status = 'done'
                            WHERE id = %s
                        """, (embedding, chunk_id))
                log.info("embeddings_written", count=len(ids))

            except Exception as exc:
                log.error("embedding_batch_failed", error=str(exc), batch_size=len(ids))
                async with pool.connection() as conn:
                    for chunk_id in ids:
                        new_count = retry_counts[chunk_id] + 1
                        new_status = "failed" if new_count >= retry_max else "pending"
                        await conn.execute("""
                            UPDATE chunks
                            SET embedding_status = %s, retry_count = %s
                            WHERE id = %s
                        """, (new_status, new_count, chunk_id))

        except Exception as exc:
            log.error("embedding_worker_error", error=str(exc))
            await asyncio.sleep(EMBED_POLL_INTERVAL * 5)

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

EMBED_POLL_INTERVAL = 1   # seconds between DB polls
_CONSECUTIVE_ERROR_THRESHOLD = 10  # circuit breaker trips after this many failures
_CIRCUIT_BREAKER_BACKOFF = 60  # seconds to wait when circuit breaker trips
# Tune based on available RAM and Ollama model size
# Larger batches = more memory but faster throughput
# 200 = ~50-100MB for nomic-embed-text
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
        if resp.status_code != 200:
            log.error("ollama_request_failed", status=resp.status_code, response=resp.text[:500], batch_size=len(texts))
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
    consecutive_errors = 0
    while True:
        try:
            async with pool.connection() as conn:
                # Atomic claim with FOR UPDATE SKIP LOCKED
                rows = await (await conn.execute("""
                    UPDATE chunks SET embedding_status = 'processing'
                    WHERE id IN (
                        SELECT id FROM chunks
                        WHERE embedding_status = 'pending'
                        ORDER BY id
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, text, retry_count
                """, (EMBED_BATCH_SIZE,))).fetchall()

            if not rows:
                await asyncio.sleep(EMBED_POLL_INTERVAL)
                continue

            ids = [str(r[0]) for r in rows]
            texts = [r[1] for r in rows]
            retry_counts = {str(r[0]): r[2] for r in rows}

            try:
                import time
                start_time = time.time()
                embeddings = await call_ollama_embed(ollama_url, model, texts)
                ollama_latency_ms = (time.time() - start_time) * 1000
                
                async with pool.connection() as conn:
                    db_start = time.time()
                    # Batch UPDATE via individual executes (psycopg3 AsyncConnection doesn't have executemany)
                    for cid, emb in zip(ids, embeddings, strict=True):
                        await conn.execute("""
                            UPDATE chunks
                            SET embedding = %s,
                                embedded_at = now(),
                                embedding_status = 'done'
                            WHERE id = %s
                        """, (emb, cid))
                    db_latency_ms = (time.time() - db_start) * 1000
                
                log.info("embeddings_written", 
                    count=len(ids), 
                    ollama_latency_ms=ollama_latency_ms,
                    db_write_latency_ms=db_latency_ms,
                    avg_latency_per_chunk_ms=ollama_latency_ms/len(ids))

            except Exception as exc:
                failed_count = sum(1 for chunk_id in ids if retry_counts[chunk_id] >= retry_max - 1)
                log.error("embedding_batch_failed", 
                    error=str(exc), 
                    batch_size=len(ids),
                    will_fail=failed_count,
                    error_type=type(exc).__name__)
                async with pool.connection() as conn:
                    for chunk_id in ids:
                        new_count = retry_counts[chunk_id] + 1
                        new_status = "failed" if new_count >= retry_max else "pending"
                        await conn.execute("""
                            UPDATE chunks
                            SET embedding_status = %s, retry_count = %s
                            WHERE id = %s
                        """, (new_status, new_count, chunk_id))

            consecutive_errors = 0  # reset on successful iteration

        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors >= _CONSECUTIVE_ERROR_THRESHOLD:
                log.error("embedding_circuit_breaker_open",
                    error=str(exc),
                    consecutive_errors=consecutive_errors,
                    backoff_s=_CIRCUIT_BREAKER_BACKOFF)
                await asyncio.sleep(_CIRCUIT_BREAKER_BACKOFF)
                consecutive_errors = 0
            else:
                log.error("embedding_worker_error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    consecutive_errors=consecutive_errors)
                await asyncio.sleep(EMBED_POLL_INTERVAL * 5)

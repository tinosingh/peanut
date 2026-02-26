"""Embedding worker — asyncio Task inside ingest-worker.

Polls chunks WHERE embedding_status='pending', calls Ollama in batches,
writes embeddings back. Uses FOR UPDATE SKIP LOCKED for safe concurrent
operation if the container is accidentally double-launched.

After embed_retry_max failures (from config table, default 5),
sets embedding_status='failed' — prevents infinite retry loops.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from src.ingest.chunker import MAX_CHUNK_CHARS

log = structlog.get_logger()

EMBED_POLL_INTERVAL = 1   # seconds between DB polls
_CONSECUTIVE_ERROR_THRESHOLD = 10
_CIRCUIT_BREAKER_BACKOFF = 60

# nomic-embed-text context_length = 2048 BERT tokens.
# Worst-case (Swedish/Finnish) ≈ 1.2 chars/token → ~2,400 chars per input.
# Batching: Ollama processes each input independently, so the limit is
# per-input, NOT cumulative.  We batch up to 8 inputs at a time for
# throughput.
EMBED_BATCH_SIZE = 8


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
            log.error(
                "ollama_request_failed",
                status=resp.status_code,
                response=resp.text[:500],
                batch_size=len(texts),
            )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def _truncate_for_embed(text: str, max_chars: int = MAX_CHUNK_CHARS) -> str:
    """Truncate text to *max_chars* on a word boundary.

    This is a safety net: chunks coming out of chunk_text() should already
    respect MAX_CHUNK_CHARS, but legacy rows in the DB may not.
    """
    if len(text) <= max_chars:
        return text
    # Cut at the last space before the limit.
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    log.warning(
        "chunk_truncated_for_embed",
        original_chars=len(text),
        truncated_chars=len(truncated),
    )
    return truncated


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
            texts = [_truncate_for_embed(r[1]) for r in rows]
            retry_counts = {str(r[0]): r[2] for r in rows}

            try:
                start = time.monotonic()
                embeddings = await call_ollama_embed(ollama_url, model, texts)
                elapsed_ms = (time.monotonic() - start) * 1000

                async with pool.connection() as conn:
                    for cid, emb in zip(ids, embeddings, strict=True):
                        await conn.execute("""
                            UPDATE chunks
                            SET embedding = %s, embedded_at = now(),
                                embedding_status = 'done'
                            WHERE id = %s
                        """, (emb, cid))

                log.info(
                    "embeddings_written",
                    count=len(ids),
                    elapsed_ms=round(elapsed_ms, 1),
                )
                consecutive_errors = 0

            except httpx.HTTPStatusError as exc:
                is_context_error = (
                    exc.response.status_code == 400
                    and "context" in exc.response.text.lower()
                )

                if is_context_error and len(ids) > 1:
                    # Batch-level overflow — fall back to one-at-a-time.
                    log.warning(
                        "batch_overflow_falling_back",
                        batch_size=len(ids),
                    )
                    for cid, text in zip(ids, texts):
                        try:
                            embs = await call_ollama_embed(
                                ollama_url, model, [text]
                            )
                            async with pool.connection() as conn:
                                await conn.execute("""
                                    UPDATE chunks
                                    SET embedding = %s, embedded_at = now(),
                                        embedding_status = 'done'
                                    WHERE id = %s
                                """, (embs[0], cid))
                        except httpx.HTTPStatusError as inner:
                            new_count = retry_counts[cid] + 1
                            new_status = (
                                "failed" if new_count >= retry_max
                                else "pending"
                            )
                            async with pool.connection() as conn:
                                await conn.execute("""
                                    UPDATE chunks
                                    SET embedding_status = %s,
                                        retry_count = %s
                                    WHERE id = %s
                                """, (new_status, new_count, cid))
                            log.warning(
                                "chunk_embed_failed",
                                chunk_id=cid,
                                chars=len(text),
                                retry_count=new_count,
                                error=str(inner)[:200],
                            )
                    consecutive_errors = 0
                else:
                    # Single-chunk context error or non-context error.
                    _increment_retries(ids, retry_counts, retry_max, exc, pool)
                    await _apply_retry_updates(
                        pool, ids, retry_counts, retry_max
                    )
                    log.error(
                        "embedding_batch_failed",
                        error=str(exc)[:300],
                        batch_size=len(ids),
                    )

            except Exception as exc:
                await _apply_retry_updates(
                    pool, ids, retry_counts, retry_max
                )
                log.error(
                    "embedding_batch_failed",
                    error=str(exc)[:300],
                    batch_size=len(ids),
                    error_type=type(exc).__name__,
                )

        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors >= _CONSECUTIVE_ERROR_THRESHOLD:
                log.error(
                    "embedding_circuit_breaker_open",
                    error=str(exc),
                    consecutive_errors=consecutive_errors,
                    backoff_s=_CIRCUIT_BREAKER_BACKOFF,
                )
                await asyncio.sleep(_CIRCUIT_BREAKER_BACKOFF)
                consecutive_errors = 0
            else:
                log.error(
                    "embedding_worker_error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    consecutive_errors=consecutive_errors,
                )
                await asyncio.sleep(EMBED_POLL_INTERVAL * 5)


def _increment_retries(
    ids: list[str],
    retry_counts: dict[str, int],
    retry_max: int,
    exc: Exception,
    pool: Any,
) -> None:
    """Bump retry_counts in-place (DB update is done by _apply_retry_updates)."""
    for cid in ids:
        retry_counts[cid] = retry_counts[cid] + 1


async def _apply_retry_updates(
    pool: Any,
    ids: list[str],
    retry_counts: dict[str, int],
    retry_max: int,
) -> None:
    """Write updated retry counts / status back to the DB."""
    async with pool.connection() as conn:
        for cid in ids:
            new_count = retry_counts[cid]
            new_status = "failed" if new_count >= retry_max else "pending"
            await conn.execute("""
                UPDATE chunks SET embedding_status = %s, retry_count = %s
                WHERE id = %s
            """, (new_status, new_count, cid))

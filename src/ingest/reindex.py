"""Re-embed all chunks into embedding_v2 column for zero-downtime model swap.

Usage (via Makefile):
    make reindex
    # Which runs: docker exec ingest-worker python -m src.ingest.reindex

Pipeline:
  1. Select chunks WHERE embedding_v2 IS NULL AND embedding_status='done'
     using FOR UPDATE SKIP LOCKED (safe for concurrent runs)
  2. Embed via Ollama /api/embed
  3. Write to embedding_v2 column
  4. After all chunks done, prompt operator for atomic rename:
     embedding → embedding_old, embedding_v2 → embedding

The atomic rename requires --confirm flag to prevent accidental execution.
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
import structlog

log = structlog.get_logger()

BATCH_SIZE = 50
REINDEX_MODEL_ENV = "EMBED_MODEL_V2"  # override model for v2; falls back to EMBED_MODEL


async def _embed_batch(ollama_url: str, model: str, texts: list[str]) -> list[list[float]] | None:
    """Call Ollama /api/embed for a batch of texts."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            embeddings = []
            for text in texts:
                resp = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                resp.raise_for_status()
                embeddings.append(resp.json()["embedding"])
            return embeddings
    except Exception as exc:
        log.error("reindex_embed_failed", error=str(exc))
        return None


async def reindex(confirm_rename: bool = False) -> None:
    """Re-embed all chunks to embedding_v2. Optionally rename columns."""
    from src.shared.db import close_pool, get_pool

    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    model = os.getenv(REINDEX_MODEL_ENV) or os.getenv("EMBED_MODEL", "nomic-embed-text")

    pool = await get_pool()
    log.info("reindex_start", model=model, ollama_url=ollama_url)

    total = 0
    while True:
        async with pool.connection() as conn:
            rows = await (await conn.execute(
                """
                SELECT id::text, text
                FROM chunks
                WHERE embedding_v2 IS NULL
                  AND embedding_status = 'done'
                ORDER BY id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (BATCH_SIZE,),
            )).fetchall()

        if not rows:
            break

        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]

        embeddings = await _embed_batch(ollama_url, model, texts)
        if embeddings is None:
            log.error("reindex_batch_failed", count=len(ids))
            continue

        async with pool.connection() as conn:
            for chunk_id, emb in zip(ids, embeddings, strict=False):
                await conn.execute(
                    "UPDATE chunks SET embedding_v2 = %s::vector WHERE id = %s::uuid",
                    (emb, chunk_id),
                )

        total += len(ids)
        log.info("reindex_progress", embedded=total)

    log.info("reindex_complete", total_embedded=total)

    if confirm_rename:
        log.info("reindex_rename_start")
        async with pool.connection() as conn:
            # Atomic: rename embedding → embedding_old, embedding_v2 → embedding
            await conn.execute(
                """
                ALTER TABLE chunks
                  RENAME COLUMN embedding TO embedding_old;
                ALTER TABLE chunks
                  RENAME COLUMN embedding_v2 TO embedding;
                ALTER TABLE chunks
                  DROP COLUMN embedding_old;
                """
            )
        log.info("reindex_rename_complete")
    else:
        log.info(
            "reindex_rename_skipped",
            hint="Run with --confirm to atomically swap embedding and embedding_v2",
        )

    await close_pool()


def main() -> None:
    confirm = "--confirm" in sys.argv
    if confirm:
        print("WARNING: --confirm passed. embedding and embedding_v2 will be renamed atomically.")
        print("Press Ctrl-C within 5 seconds to abort...")
        import time
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("Aborted.")
            sys.exit(0)
    asyncio.run(reindex(confirm_rename=confirm))


if __name__ == "__main__":
    main()

"""Ingest worker entry point — wires watcher, embedding worker, outbox worker."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from datetime import UTC, datetime

import structlog

log = structlog.get_logger()


async def _insert_chunks(pool, doc_id: str, chunks, pii_flags: list[bool]) -> None:
    """Insert Chunk objects with embedding_status='pending'."""
    async with pool.connection() as conn:
        for chunk, pii in zip(chunks, pii_flags, strict=False):
            await conn.execute(
                """
                INSERT INTO chunks (id, doc_id, chunk_index, text, pii_detected)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (doc_id, chunk_index) DO NOTHING
                """,
                (str(uuid.uuid4()), doc_id, chunk.index, chunk.text, pii),
            )


async def _handle_file(path: str, sha: str) -> None:
    """Called by watcher for each new file; runs full ingest pipeline."""
    from src.ingest.chunker import chunk_text
    from src.ingest.db import ingest_document, sha256_exists
    from src.ingest.parsers.detector import detect_type
    from src.ingest.parsers.markdown_parser import parse_markdown
    from src.ingest.parsers.mbox import parse_mbox
    from src.ingest.parsers.pdf import parse_pdf
    from src.ingest.pii import has_pii
    from src.ingest.vault_sync import write_document_note
    from src.shared.config import get_config
    from src.shared.db import get_pool

    log.info("ingest_file_start", path=path, sha=sha)
    pool = await get_pool()

    if await sha256_exists(pool, sha):
        log.info("ingest_skip_duplicate", path=path)
        return

    cfg = await get_config(pool)
    chunk_size = int(cfg.get("chunk_size", 512))
    chunk_overlap = int(cfg.get("chunk_overlap", 50))
    vault_sync_path = os.getenv("VAULT_SYNC_PATH", "./vault-sync")
    now = datetime.now(UTC)

    try:
        file_type = detect_type(path)
        if file_type == "mbox":
            for item in parse_mbox(path):
                if isinstance(item, Exception):
                    log.warning("mbox_parse_error", path=path, error=str(item))
                    continue
                text = item.body_text or ""
                chunks = chunk_text(text, chunk_size, chunk_overlap)
                pii_flags = [has_pii(c.text) for c in chunks]
                doc_id = await ingest_document(
                    pool,
                    source_path=path,
                    source_type="mbox",
                    sha256=sha,
                    sender_email=item.sender_email or "",
                    sender_name=item.sender_name or "",
                    recipients=item.recipients,
                    metadata={"subject": item.subject, "sender_email": item.sender_email},
                )
                await _insert_chunks(pool, doc_id, chunks, pii_flags)
                write_document_note(
                    vault_sync_path,
                    doc_id=doc_id,
                    source_path=path,
                    source_type="mbox",
                    sender_email=item.sender_email or "",
                    subject=item.subject or "",
                    ingested_at=now,
                )

        elif file_type == "pdf":
            text = parse_pdf(path)
            chunks = chunk_text(text, chunk_size, chunk_overlap)
            pii_flags = [has_pii(c.text) for c in chunks]
            doc_id = await ingest_document(
                pool,
                source_path=path, source_type="pdf", sha256=sha,
                sender_email="", sender_name="", recipients=[],
                metadata={"subject": os.path.basename(path)},
            )
            await _insert_chunks(pool, doc_id, chunks, pii_flags)

        elif file_type in ("markdown", "text"):
            text = parse_markdown(path)
            chunks = chunk_text(text, chunk_size, chunk_overlap)
            pii_flags = [has_pii(c.text) for c in chunks]
            doc_id = await ingest_document(
                pool,
                source_path=path, source_type="markdown", sha256=sha,
                sender_email="", sender_name="", recipients=[],
                metadata={"subject": os.path.basename(path)},
            )
            await _insert_chunks(pool, doc_id, chunks, pii_flags)

        else:
            from src.ingest.db import write_dead_letter
            await write_dead_letter(pool, path, f"unsupported file type: {file_type}")
            log.warning("ingest_unsupported_type", path=path, file_type=file_type)

    except Exception as exc:
        log.error("ingest_file_failed", path=path, error=str(exc))
        try:
            from src.ingest.db import write_dead_letter
            await write_dead_letter(pool, path, str(exc))
        except Exception:
            pass


async def main() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
        )
    )
    log.info("ingest_worker_starting")

    from src.ingest.embedding_worker import embedding_worker
    from src.ingest.outbox_worker import outbox_worker
    from src.ingest.watcher import watch_drop_zone
    from src.shared.db import close_pool, get_pool

    drop_zone = os.getenv("DROP_ZONE_PATH", "/drop-zone")
    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    embed_model = os.getenv("EMBED_MODEL", "nomic-embed-text")
    falkordb_host = os.getenv("FALKORDB_HOST", "pkg-graph")
    falkordb_port = int(os.getenv("FALKORDB_PORT", "6379"))

    pool = await get_pool()
    log.info("db_pool_ready")

    stop_event = asyncio.Event()

    def _handle_signal(sig: int, _frame) -> None:  # noqa: ARG001
        log.info("ingest_worker_shutting_down", signal=sig)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    async def _watcher_task() -> None:
        await watch_drop_zone(drop_zone, _handle_file)

    tasks = [
        asyncio.create_task(_watcher_task(), name="watcher"),
        asyncio.create_task(
            embedding_worker(pool, ollama_url, embed_model), name="embedding_worker"
        ),
        asyncio.create_task(
            outbox_worker(pool, falkordb_host, falkordb_port), name="outbox_worker"
        ),
    ]
    log.info("all_workers_started", drop_zone=drop_zone)

    try:
        await asyncio.wait(
            [asyncio.create_task(stop_event.wait()), *tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await close_pool()
        log.info("ingest_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())

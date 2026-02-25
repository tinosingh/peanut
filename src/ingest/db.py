"""Ingest-worker DB operations.

ALL writes within ingest_document() execute in a SINGLE transaction:
  - documents INSERT
  - persons UPSERT (sender + all recipients)
  - outbox INSERT (with sender + recipients[] payload)

This ensures Postgres and FalkorDB stay consistent even on crash.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

log = structlog.get_logger()


async def sha256_exists(pool: AsyncConnectionPool, sha256: str) -> bool:
    """Return True if this sha256 is already in documents (dedup)."""
    async with pool.connection() as conn:
        result = await conn.execute(
            "SELECT 1 FROM documents WHERE sha256 = %s", (sha256,)
        )
        row = await result.fetchone()
        return row is not None


async def ingest_document(
    pool: AsyncConnectionPool,
    *,
    source_path: str,
    source_type: str,    # 'mbox' | 'pdf' | 'markdown'
    sha256: str,
    sender_email: str,
    sender_name: str,
    recipients: list[dict],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Insert document, UPSERT persons, INSERT outbox event — all in one transaction.

    Returns the new document UUID.
    """
    doc_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    async with pool.connection() as conn, conn.transaction():
        # 1. Insert document
        await conn.execute(
            """
                INSERT INTO documents (id, source_path, source_type, sha256, ingested_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
            (doc_id, source_path, source_type, sha256, now, json.dumps(metadata or {})),
        )

        # 2. UPSERT sender
        sender_id = str(uuid.uuid4())
        await conn.execute(
            """
                INSERT INTO persons (id, email, display_name, pii)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (email) DO UPDATE SET
                    display_name = EXCLUDED.display_name
                """,
            (sender_id, sender_email, sender_name or sender_email),
        )
        # Fetch real id (may differ from sender_id if conflict)
        result = await conn.execute("SELECT id FROM persons WHERE email = %s", (sender_email,))
        row = await result.fetchone()
        sender_pg_id = str(row[0]) if row else sender_id

        # 3. UPSERT all recipients
        for r in recipients:
            await conn.execute(
                """
                    INSERT INTO persons (id, email, display_name, pii)
                    VALUES (%s, %s, %s, true)
                    ON CONFLICT (email) DO NOTHING
                    """,
                (str(uuid.uuid4()), r["email"], r.get("name") or r["email"]),
            )

        # 4. INSERT outbox event (graph write deferred to outbox worker)
        outbox_payload = {
            "doc_id": doc_id,
            "source_path": source_path,
            "source_type": source_type,
            "ingested_at": now.isoformat(),
            "sender": {"email": sender_email, "name": sender_name, "id": sender_pg_id},
            "recipients": recipients,
        }
        await conn.execute(
            """
                INSERT INTO outbox (event_type, payload, created_at)
                VALUES ('document_added', %s, %s)
                """,
            (json.dumps(outbox_payload), now),
        )

    log.info("document_ingested", doc_id=doc_id, source_path=source_path)
    return doc_id


async def write_dead_letter(pool: AsyncConnectionPool, file_path: str, error: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO dead_letter (file_path, error)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (file_path, error),
        )
